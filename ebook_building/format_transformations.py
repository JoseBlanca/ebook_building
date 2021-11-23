
import subprocess
import platform

if platform.system() == 'Darwin':
    EBOOK_CONVERT_BIN = '/Applications/calibre.app/Contents/MacOS/ebook-convert'
else:
    EBOOK_CONVERT_BIN = 'ebook-convert'


def epub_to_azw3(epub_path, azw3_path):
    cmd = [EBOOK_CONVERT_BIN, str(epub_path), str(azw3_path)]
    subprocess.run(cmd, check=True)


def epub_to_mobi(epub_path, mobi_path):
    cmd = [EBOOK_CONVERT_BIN, str(epub_path), str(mobi_path)]
    subprocess.run(cmd, check=True)


def epub_to_pdf(epub_path, pdf_path):
    # incluir números de página
    # título de capítulo si se puede
    cmd = [EBOOK_CONVERT_BIN, str(epub_path), str(pdf_path),
           #'--output-profile', 'tablet',
           '--pdf-page-numbers',
           #'--pdf-header-template', '<p>_PAGENUM_ _SECTION_</p>',
           #'--unit', 'inch', '--custom-size', '6x9',
           #'--base-font-size', '9',
           #'--extra-css', 'h2 {font-size: 1.5em; text-transform: uppercase;}'
          ]
    subprocess.run(cmd, check=True)
