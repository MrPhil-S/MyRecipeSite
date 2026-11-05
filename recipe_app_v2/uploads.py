"""Validate uploads and store all persistent media under one root."""
import io
import os
import secrets
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import ROOT

MAX_UPLOAD = 8 * 1024 * 1024


def upload_root():
    return Path(os.environ.get('RECIPE_UPLOADS', ROOT / 'recipe_app_v2/uploads'))


def image_bytes(data):
    if not data:
        return None
    if len(data) > MAX_UPLOAD:
        raise ValueError('Image must be at most 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG') or image.width * image.height > 20000000:
                    raise ValueError('Upload a JPEG or PNG image of at most 20 million pixels.')
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1000, 1000))
                # Re-encode pixels without user-supplied metadata or filenames.
                pixels = Image.new('RGB', image.size, 'white')
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    image = image.convert('RGBA')
                    pixels.paste(image, mask=image.getchannel('A'))
                else:
                    pixels.paste(image.convert('RGB'))
                output = io.BytesIO()
                pixels.save(output, format='JPEG', quality=90)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ValueError('Upload a valid JPEG or PNG image.') from None


def pdf_bytes(data):
    if not data:
        return None
    if len(data) > MAX_UPLOAD:
        raise ValueError('PDF must be at most 8 MB.')
    if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]:
        raise ValueError('Upload a PDF file with a valid header and end marker.')
    return data


class StagedUploads:
    """Undo file replacements when the associated database save fails.

    Database and filesystem do not share a crash-atomic transaction. Existing
    images are retained; PDF replacements keep their previous version on disk.
    """
    def __init__(self):
        self.created_image = None
        self.pdf_path = None
        self.pdf_backup = None
        self.pdf_created = False

    def apply(self, recipe, image, pdf):
        root = upload_root()
        if image:
            directory = root / 'images'
            directory.mkdir(parents=True, exist_ok=True)
            filename = secrets.token_hex(8) + '.jpg'
            image_path = directory / filename
            with image_path.open('xb') as target:
                self.created_image = image_path
                target.write(image)
            recipe.image_file = filename
        if pdf:
            directory = root / 'pdfs'
            directory.mkdir(parents=True, exist_ok=True)
            self.pdf_path = directory / f'{recipe.recipe_id}.pdf'
            pending = directory / (secrets.token_hex(16) + '.pending')
            try:
                with pending.open('xb') as target:
                    target.write(pdf)
                if self.pdf_path.exists():
                    self.pdf_backup = directory / (f'{recipe.recipe_id}.' + secrets.token_hex(8) + '.previous')
                    os.replace(self.pdf_path, self.pdf_backup)
                os.replace(pending, self.pdf_path)
                self.pdf_created = True
            finally:
                pending.unlink(missing_ok=True)

    def rollback(self):
        if self.created_image:
            self.created_image.unlink(missing_ok=True)
        if self.pdf_created:
            self.pdf_path.unlink(missing_ok=True)
        if self.pdf_backup and self.pdf_backup.exists():
            os.replace(self.pdf_backup, self.pdf_path)
