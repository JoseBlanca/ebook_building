

from pathlib import Path
import zipfile
import re

from bs4 import BeautifulSoup

FOOTNOTES_SECTION_CLASS = 'footnotes'
FOOTNOTE_ANCHOR_CLASS = 'footnote-ref'


def _is_html(data):
    if isinstance(data, str):
        return '<!DOCTYPE html>' in data
    else:
        return b'<!DOCTYPE html>' in data


def _get_encoding(data):
    pattern = 'encoding=["\'](.+)["\']'
    if isinstance(data, str):
        match = re.search(pattern, data, re.IGNORECASE)
    else:
        match = re.search(pattern.encode(), data, re.IGNORECASE)

    if match is None:
        msg = 'No encoding declaration found'
        raise RuntimeError(msg)

    match = match.group(1)
    if not isinstance(match, str):
        match = match.decode()

    return match.lower()


def _data_to_str(data, encoding=None):

    if isinstance(data, str):
        return data

    if encoding is None:
        encoding = _get_encoding(data)

    return data.decode(encoding)


def _data_to_bytes(data, encoding=None):
    if not isinstance(data, str):
        return data

    if encoding is None:
        encoding = _get_encoding(data)

    return data.encode(encoding)


def _is_html_with_encoding(data):
    if not _is_html(data):
        return False
    try:
        encoding = _get_encoding(data)
    except RuntimeError:
        return False
    return True


class Content:
    def __init__(self, info, data):
        self.info = info
        self.absolute_path = info.filename
        self.data = data

    def path_from(self, content):
        sep = '/'
        to_path = self.absolute_path.split(sep)
        from_path = content.absolute_path.split(sep)

        common_path = []
        for to_bit, from_bit in zip(to_path, from_path):
            if to_bit == from_bit:
                common_path.append(to_bit)

        to_path = to_path[len(common_path):]
        from_path = from_path[len(common_path):]

        if not to_path:
            path_from = ''
        elif len(to_path) == 1 and len(from_path) == 1:
            if common_path[-1].lower() == 'text':
                path_from = '..' + sep + common_path[-1] + sep +  to_path[0]
            else:
                path_from = to_path[0]
        else:
            raise NotImplementedError('Fixme for when files are not in the same dir')

        return path_from


class BookSection(Content):

    def __init__(self, info, data):
        super().__init__(info, data)
        self.data = _data_to_str(data)

    @property
    def id(self):
        soup = BeautifulSoup(self.data, "xml")
        section = soup.section
        if section is None:
            raise RuntimeError('No section present')
        try:
            return section['id']
        except KeyError:
            raise RuntimeError('Section has no id')

    @property
    def title(self):
        soup = BeautifulSoup(self.data, "xml")
        h1 = soup.h1

        span = h1.span
        if span:
            title = str(h1.contents[-1].string)
        else:
            title = str(h1.string)
        title = title.strip()
        return title
 
    def remove_and_return_footnotes_section(self):
        soup = BeautifulSoup(self.data, "xml")

        bs_tags = soup.find_all(class_=FOOTNOTES_SECTION_CLASS)
        if not bs_tags:
            raise RuntimeError('No footnote seccion')
        if len(bs_tags) != 1:
            raise RuntimeError('Only one footnote section expected')
        assert bs_tags[0].name == 'section'
        section = bs_tags[0]

        section.extract()
        #section.replace_with('')

        self.data = soup.prettify()

        return section

    def modify_footnote_links(self, global_footnote_count, path_to_notes_chapter):
        soup = BeautifulSoup(self.data, "xml")

        footnotes_info = []
        for anchor_tag in soup.find_all('a', class_=FOOTNOTE_ANCHOR_CLASS):
            new_id = 'fn' + str(global_footnote_count + 1)
            footnote = {'old_id': anchor_tag.attrs['href'].split('#')[-1],
                        'new_id': new_id}
            reference_to_footnote_in_text = {'id': anchor_tag.attrs['id']}
            footnotes_info.append({'footnote': footnote,
                                   'reference_to_footnote_in_text': reference_to_footnote_in_text})
            global_footnote_count += 1

            new_href = f'{path_to_notes_chapter}#{new_id}'
            anchor_tag.attrs['href'] = new_href

        self.data = soup.prettify()

        return footnotes_info, global_footnote_count


class _Epub:
    def __init__(self, in_path):
        self.contents = []
        self._sections_by_id = {}

        self._read(in_path)
        #self.contents[-1].data = self.contents[-1].data

    def _read(self, path):
        zip_file = zipfile.ZipFile(path, 'r')
        for info in zip_file.infolist():
            data = zip_file.read(info)

            content = None
            if _is_html_with_encoding(data):
                try:
                    content = BookSection(info, data)
                except RuntimeError:
                    pass

            if content is None:
                content = Content(info, data)
            else:
                try:
                    self._sections_by_id[content.id] = content
                except RuntimeError:
                    pass

            self.contents.append(content)

    def write(self, path):
        with zipfile.ZipFile(path, 'w') as zip_file:
            for content in self.contents:
                zip_file.writestr(content.info,
                                  _data_to_bytes(content.data))

    def get_section_by_id(self, id):
        return self._sections_by_id[id]


class Epub(_Epub):
    
    def __init__(self, in_path, bibliography_chapter_id, notes_chapter_id):
        self.bibliography_chapter_id = bibliography_chapter_id
        self.notes_chapter_id = notes_chapter_id
        super().__init__(in_path=in_path)

    @property
    def bibliography_chapter(self):
        return self.get_section_by_id(self.bibliography_chapter_id)

    @property
    def notes_chapter(self):
        return self.get_section_by_id(self.notes_chapter_id)

    def _modify_footnotes_id_and_backlinks(self, footnote_section, chapter,
                                           info_about_footnotes_in_chapter,
                                           footnotes_chapter):

        footnotes_in_chapter_by_old_id = {}
        for info in info_about_footnotes_in_chapter:
            old_id = info['footnote']['old_id']
            footnotes_in_chapter_by_old_id[old_id] = info

        for li in footnote_section.find_all('li'):
            old_footnote_id = li.attrs['id']
            footnote_in_chapter_info = footnotes_in_chapter_by_old_id[old_footnote_id]
            li.attrs['id'] = footnote_in_chapter_info['footnote']['new_id']

            back_to_chapter_anchor = li.find_all('a', class_='footnote-back')[0]
            new_back_href = chapter.path_from(footnotes_chapter) + '#' + footnote_in_chapter_info['reference_to_footnote_in_text']['id']
            back_to_chapter_anchor.attrs['href'] = new_back_href

    def _appennd_notes(self, notes_chapter, chapter_footnotes):
        soup = BeautifulSoup(notes_chapter.data, "xml")

        h1s = soup.find_all('h1')
        if not h1s:
            raise RuntimeError('No H1')
        if len(h1s) > 1:
            raise RecursionError('More than one H1')
        h1 = h1s[0]

        notes_html = ''
        for res in chapter_footnotes:
            chapter = res['chapter']
            footnotes = res['footnotes']
            info_about_footnotes_in_chapter = res['info_about_footnotes_in_chapter']
            notes_html += f'<h2>{chapter.title}</h2>\n'
            self._modify_footnotes_id_and_backlinks(footnotes,
                                                    chapter,
                                                    info_about_footnotes_in_chapter,
                                                    notes_chapter)
            notes_html += str(footnotes)
            notes_html += '\n'

        h1.insert_after(notes_html)
        notes_chapter.data = soup.prettify(formatter=None)

    def collect_footnotes_in_footnotes_chapter(self):
        notes_chapter = self.notes_chapter

        chapters_with_footnotes = []
        global_footnote_count = 0
        for chapter in self._sections_by_id.values():
            try:
                chapter_footnotes = chapter.remove_and_return_footnotes_section()
            except RuntimeError:
                continue

            path_to_notes_chapter = notes_chapter.path_from(chapter)
            chapter_footnotes_info, global_footnote_count = chapter.modify_footnote_links(global_footnote_count,
                                                                                          path_to_notes_chapter)

            chapters_with_footnotes.append({'chapter': chapter,
                                            'footnotes': chapter_footnotes,
                                            'info_about_footnotes_in_chapter': chapter_footnotes_info})

        self._appennd_notes(notes_chapter, chapters_with_footnotes)
        #print(chapter_footnotes)


def move_notes_from_each_chapter_to_notes_chapter(in_epub_path, out_epub_path,
                                                  bibliography_chapter_id,
                                                  notes_chapter_id):
    epub = Epub(in_epub_path,
                bibliography_chapter_id=bibliography_chapter_id,
                notes_chapter_id=notes_chapter_id)
    epub.collect_footnotes_in_footnotes_chapter()
    epub.write(out_epub_path)


if __name__ == '__main__':
    import sys
    argv = sys.argv
    if len(argv) != 3:
        print(f'Usage: {__file__} in_epub out_epub')
        sys.exit(1)
    else:
        in_epub_path = Path(sys.argv[1])
        out_epub_path = Path(sys.argv[2])
    move_notes_from_each_chapter_to_notes_chapter(in_epub_path=in_epub_path,
                                                  out_epub_path=out_epub_path,
                                                  bibliography_chapter_id='bibliografia',
                                                  notes_chapter_id='notas')
