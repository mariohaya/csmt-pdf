import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from csmt_pdf.cli import main
from csmt_pdf.compress import CompressionError, PRESETS, compress_pdf


def make_pdf(path):
    """One-page PDF with a raw RGB image; no test dependencies."""
    pixels = bytes(range(256)) * 3072  # 512 x 512 RGB
    content = b'q 512 0 0 512 0 0 cm /Im0 Do Q'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 512 512] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /XObject /Subtype /Image /Width 512 /Height 512 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length ' + str(len(pixels)).encode() + b' >>\nstream\n' + pixels + b'\nendstream',
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream',
    ]
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path.write_bytes(data)


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'test with spaces.pdf'
        make_pdf(self.path)

    def test_missing_dependency(self):
        with patch('csmt_pdf.compress.shutil.which', return_value=None):
            with self.assertRaisesRegex(CompressionError, 'pacman'):
                compress_pdf(self.path, 'somewhat')

    def test_bad_input(self):
        with self.assertRaises(CompressionError):
            compress_pdf(self.path, 'invalid')
        with self.assertRaises(CompressionError):
            compress_pdf(self.path.parent / 'absent.pdf', 'a lot')
        self.path.write_text('not a PDF')
        with self.assertRaises(CompressionError):
            compress_pdf(self.path, 'a lot')

    def test_failure_cleans_up(self):
        with patch('csmt_pdf.compress.shutil.which', return_value='/usr/bin/gs'), patch(
            'csmt_pdf.compress.subprocess.run', return_value=subprocess.CompletedProcess([], 1)
        ):
            with self.assertRaises(CompressionError):
                compress_pdf(self.path, 'somewhat')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_larger_output_discarded(self):
        def write_large(command, **kwargs):
            output = next(arg.split('=', 1)[1] for arg in command if arg.startswith('-sOutputFile='))
            Path(output).write_bytes(self.path.read_bytes() + b'padding')
            return subprocess.CompletedProcess(command, 0)
        with patch('csmt_pdf.compress.shutil.which', return_value='/usr/bin/gs'), patch(
            'csmt_pdf.compress.subprocess.run', side_effect=write_large
        ):
            self.assertIsNone(compress_pdf(self.path, 'a lot').output)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    @unittest.skipUnless(shutil.which('gs'), 'Ghostscript is not installed')
    def test_real_compression_all_levels_no_overwrite(self):
        original = self.path.read_bytes()
        existing = self.path.with_name('test with spaces_compressed.pdf')
        existing.write_bytes(b'keep me')
        for index, level in enumerate(PRESETS, 1):
            with self.subTest(level=level):
                result = compress_pdf(self.path, level)
                self.assertEqual(result.output.name, f'test with spaces_compressed_{index}.pdf')
                self.assertLess(result.compressed_bytes, len(original))
                subprocess.run(['gs', '-q', '-dBATCH', '-dNOPAUSE', '-dPDFSTOPONERROR',
                                '-sDEVICE=nullpage', str(result.output)], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(existing.read_bytes(), b'keep me')

    @unittest.skipUnless(shutil.which('gs'), 'Ghostscript is not installed')
    def test_menu(self):
        with patch('builtins.input', side_effect=['bad', '1', str(self.path), '2']), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([]), 0)
        self.assertIn('Compressed! Saved as:', out.getvalue())

    def test_unimplemented_and_cancel(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['split']), 2)
            with patch('builtins.input', side_effect=EOFError):
                self.assertEqual(main(['compress']), 130)


if __name__ == '__main__':
    unittest.main()
