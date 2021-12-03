
from datetime import datetime
import shutil
from subprocess import run
import tempfile
from pathlib import Path
import zipfile

from ruamel.yaml import YAML

BOOKDOWN_INDEX_RMD_FNAME = 'index.Rmd'
BOOKDOWN_YML_FNAME = '_bookdown.yml'
MK_SUFFIX = '.md'

R_COMPILE_SCRIPT_EPUB = '''
setwd("{working_dir}")
index_rmd_path = file.path('{index_rmd_path}')
output_dir = file.path('{output_dir}')

bookdown::render_book(input=index_rmd_path,
                      {renderer_param},
                      output_dir = output_dir)
'''

FRONT_MATTER_TEMPLATE = '''
# Sobre el libro {{-#front_matter}}

{title}

{author}

Version: {commit_hash}

Fecha: {day}-{month}-{year}

©{copyright_date_str}, Jose Blanca. Algunos derechos reservados.

Excepto cuando se indique lo contrario, esta obra está bajo una licencia CC BY-NC-SA 4.0. (https://creativecommons.org/licenses/by-nc-sa/4.0/deed.es)

Usted es libre de:

  - Compartir — copiar y redistribuir el material en cualquier medio o formato
  - Adaptar — remezclar, transformar y construir a partir del material

El licenciante no puede revocar estas libertades en tanto usted siga los términos de la licencia bajo los siguientes términos:

  - Atribución — Usted debe dar crédito de manera adecuada, brindar un enlace a la licencia, e indicar si se han realizado cambios. Puede hacerlo en cualquier forma razonable, pero no de forma tal que sugiera que usted o su uso tienen el apoyo del licenciante.
  - NoComercial — Usted no puede hacer uso del material con propósitos comerciales.
  - CompartirIgual — Si remezcla, transforma o crea a partir del material, debe distribuir su contribución bajo la la misma licencia del original.

No hay restricciones adicionales

  — No puede aplicar términos legales ni medidas tecnológicas que restrinjan legalmente a otras a hacer cualquier uso permitido por la licencia.

Avisos:

- No tiene que cumplir con la licencia para elementos del material en el dominio público o cuando su uso esté permitido por una excepción o limitación aplicable.
- No se dan garantías. La licencia podría no darle todos los permisos que necesita para el uso que tenga previsto. Por ejemplo, otros derechos como publicidad, privacidad, o derechos morales pueden limitar la forma en que utilice el material.
'''


def run_r_command(r_cmd:str):

    cmd = ['R', '-e', f"{r_cmd}"]
    process = run(cmd, capture_output=True, check=True)
    stdout = process.stdout.decode()
    return {'stdout': stdout}


def run_rscript(r_script_str, dir_=None):
    with tempfile.NamedTemporaryFile(suffix='.R', dir=dir_) as r_script_file:
        fpath = open(r_script_file.name, 'wt')
        fpath.write(r_script_str)
        fpath.flush()
        cmd = ['Rscript', r_script_file.name]
        run(cmd, check=True, cwd=dir_)


def install_r_packages(package_names):

    for package in package_names:
        r_cmd = f'if(!require({package})) install.packages(c("{package}"))'
        run_r_command(r_cmd)


def _create_bookdown_index_rmd(index_rmd_path, book_metadata):

    METADATA_FIELDS = ['title', 'author', 'description', 'biblio-title',
                       'bibliography', 'csl']

    data = {field: value for field, value in book_metadata.items() if field in METADATA_FIELDS}
    data['site'] = 'bookdown::bookdown_site'
    data['documentclass'] = 'book'
    data['link-citations'] = 'yes'
    data['language'] = {'ui': {'chapter_name': ''}}

    fhand = index_rmd_path.open('wt')
    fhand.write('---\n')
    yaml = YAML()
    yaml.dump(data, fhand)
    fhand.write('\n---\n')
    fhand.flush()


def _get_chapter_md_paths(md_files_dir, chapters_to_exclude):
    section_dirs = []
    chapter_paths = []
    for fname in md_files_dir.iterdir():
        path = md_files_dir / fname
        if path.is_dir():
            section_dirs.append(path)
        elif path.suffix == MK_SUFFIX:
            chapter_paths.append(path)

    section_dirs.sort(key=str)

    for section_dir in section_dirs:
        this_chapter_paths = []
        for fname in section_dir.iterdir():
            path = section_dir / fname
            if path.suffix == MK_SUFFIX:
                this_chapter_paths.append(path)
        this_chapter_paths.sort(key=str)
        chapter_paths.extend(this_chapter_paths)

    chapter_paths = [path for path in chapter_paths if path.name not in chapters_to_exclude]
    return chapter_paths


def _create_bookdown_yml(bookdown_yml_path, chapter_paths):
    data = {'rmd_files': [str(path) for path in chapter_paths]}
 
    yaml = YAML()
    fhand = bookdown_yml_path.open('wt')
    yaml.dump(data, fhand)
    fhand.flush()


def _create_front_matter_chapter(metadata, front_matter_path):

    now = datetime.now()
    this_year = now.year
    if this_year == metadata['first_publish_year']:
        copyright_date_str = metadata['first_publish_year']
    else:
        copyright_date_str = f"{metadata['first_publish_year']}-{this_year}"

    to_write = FRONT_MATTER_TEMPLATE.format(title=metadata['title'],
                                            author=metadata['author'],
                                            commit_hash=metadata['commit_hash'],
                                            day=now.day,
                                            month=now.month,
                                            year=now.year,
                                            copyright_date_str=copyright_date_str

                                            )
    fhand = front_matter_path.open('wt')
    fhand.write(to_write)
    fhand.flush()
    return


def _dict_to_param_r_vector(params:dict):
    param_str = ','.join(f"'--{param}={value}'" for param, value in params.items())
    return f'c({param_str})'


def _build_renderer_param(render_funct:str, params=None):
    assert render_funct in ('bookdown::epub_book', 'bookdown::gitbook')

    if params is None:
        params = {}

    params_strs = []
    for param, value in params.items():
        if isinstance(value, str):
            value_str = value
        elif isinstance(value, bool):
            value_str = str(value).upper()
        elif isinstance(value, int):
            value_str = str(value)
        elif isinstance(value, dict):
            value_str = _dict_to_param_r_vector(value)
        params_strs.append(f'{param}={value_str}')
    params_str = ','.join(params_strs)
    param = f'{render_funct}({params_str})'
    return param


def _build_web_or_epub(output_type, book_metadata, md_files_dir,
                       output_path, cover_image_path=None,
                       chapters_to_exclude=None, number_sections=True, toc=True, toc_depth=1):
    install_r_packages(['bookdown'])

    if chapters_to_exclude is None:
        chapters_to_exclude = set()

    book_metadata = book_metadata.copy()

    with tempfile.TemporaryDirectory() as working_dir_bfpath:
        try:
            # it looks that with python 3.10 with TemporaryDirectory has changed its behaviour
            working_dir_path = Path(working_dir_bfpath.decode())
        except AttributeError:
            working_dir_path = Path(working_dir_bfpath)

        if 'bibliography_paths' in book_metadata:
            bibliography_tmp_files = []
            for path in book_metadata['bibliography_paths']:
                tmp_bib_file = tempfile.NamedTemporaryFile(dir=working_dir_path,
                                                           suffix=f'_{Path(path.name).name}',
                                                           delete=False)
                bibliography_tmp_files.append(tmp_bib_file.name)
                shutil.copy(path, tmp_bib_file.name)
                tmp_bib_file.close()
            book_metadata['bibliography'] = bibliography_tmp_files
            del book_metadata['bibliography_paths']
        else:
            bibliography_tmp_files = None

        if 'citation_style_language_path' in book_metadata:
            orig_path = book_metadata['citation_style_language_path']
            fname = orig_path.name
            new_path = working_dir_path / fname
            shutil.copy(orig_path, new_path)
            book_metadata['csl'] = fname
            del book_metadata['citation_style_language_path']

        index_rmd_path = working_dir_path / BOOKDOWN_INDEX_RMD_FNAME
        _create_bookdown_index_rmd(index_rmd_path, book_metadata)

        working_md_chapters_path = working_dir_path / 'chapters'
        shutil.copytree(md_files_dir, working_md_chapters_path)

        front_matter_path = working_md_chapters_path / 'front_matter.md'
        _create_front_matter_chapter(book_metadata, front_matter_path)

        chapter_paths = [index_rmd_path]
        chapter_paths.extend(_get_chapter_md_paths(working_md_chapters_path,
                                                   chapters_to_exclude))

        chapter_paths.sort(key=str)
        chapter_paths.sort(key=lambda path: 0 if 'dedicatoria.md' in str(path) else 1)
        chapter_paths.sort(key=lambda path: 0 if 'front_matter.md' in str(path) else 1)
        chapter_paths.sort(key=lambda path: 0 if 'index.Rmd' in str(path) else 1)

        bookdown_yml_path = working_dir_path / BOOKDOWN_YML_FNAME
        _create_bookdown_yml(bookdown_yml_path, chapter_paths)

        output_dir_name = 'output'
        output_dir = working_dir_path / output_dir_name

        renderer_params = {'toc_depth': toc_depth, 'number_sections': number_sections}
        if toc is not None:
            renderer_params['toc'] = toc

        if cover_image_path:
            tmp_cover_image_path = tempfile.NamedTemporaryFile(dir=working_dir_path,
                                                               suffix=cover_image_path.suffix,
                                                               delete=False)
            shutil.copy(cover_image_path, tmp_cover_image_path.name)
            tmp_cover_image_path.close()
            renderer_params['cover_image'] = f"file.path('{tmp_cover_image_path.name}')"

        if output_type == 'epub':
            render_funct = 'bookdown::epub_book'
        elif output_type == 'web':
            render_funct = 'bookdown::gitbook'
        else:
            raise ValueError(f'Uknown ouput_type, it should be web or epub, but it is: {output_type}')

        renderer_param = _build_renderer_param(render_funct,
                                               params=renderer_params)

        r_build_script = R_COMPILE_SCRIPT_EPUB.format(working_dir=working_dir_path,
                                                      index_rmd_path=index_rmd_path,
                                                      output_dir=output_dir,
                                                      renderer_param=renderer_param)
        run_rscript(r_build_script, working_dir_path)

        if output_type == 'epub':
            tmp_epub_path = output_dir / '_main.epub'
            shutil.move(tmp_epub_path, output_path)
        elif output_type == 'web':
            tmp_web_path = output_dir
            if output_path.exists():
                shutil.rmtree(output_path)
            shutil.move(tmp_web_path, output_path)

        del bibliography_tmp_files


def build_web(book_metadata, md_files_dir, output_path, cover_image_path=None,
              chapters_to_exclude=None, number_sections=True, toc_depth=1):
    _build_web_or_epub('web',
                       book_metadata=book_metadata,
                       md_files_dir=md_files_dir,
                       output_path=output_path,
                       cover_image_path=cover_image_path,
                       chapters_to_exclude=chapters_to_exclude,
                       number_sections=number_sections,
                       toc=None,
                       toc_depth=toc_depth)


def build_epub(book_metadata, md_files_dir, output_path, cover_image_path=None,
               chapters_to_exclude=None, number_sections=True, toc=True, toc_depth=1):

    _build_web_or_epub('epub',
                       book_metadata=book_metadata,
                       md_files_dir=md_files_dir,
                       output_path=output_path,
                       cover_image_path=cover_image_path,
                       chapters_to_exclude=chapters_to_exclude,
                       number_sections=number_sections,
                       toc=toc,
                       toc_depth=toc_depth)


def get_commit_hash(git_dir):
    cmd = ['git', 'rev-parse', 'HEAD']
    process = run(cmd, cwd=git_dir, capture_output=True)
    return process.stdout.decode().strip()


def unpack_epub(epub_path, out_dir):
    zipfile.ZipFile(epub_path, 'r').extractall(path=out_dir)

