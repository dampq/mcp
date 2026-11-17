import os
import tempfile
import unittest
from pathlib import Path

class ResearchCoreTests(unittest.TestCase):
    def test_index_search_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['RESEARCH_DOCS_DIR'] = str(Path(tmp) / 'docs')
            os.environ['RESEARCH_DB_PATH'] = str(Path(tmp) / 'test.db')
            import importlib
            import research_core
            core = importlib.reload(research_core)
            core.DOCUMENTS.mkdir()
            (core.DOCUMENTS / 'paper.txt').write_text('Machine learning uses training data. Frame extraction uses OpenCV.', encoding='utf8')
            self.assertEqual(core.index_all()[0]['status'], 'indexed')
            results = core.search_documents('OpenCV')
            self.assertEqual(results[0]['file'], 'paper.txt')
            self.assertIn('document', results[0]['citation'])
            with self.assertRaises(ValueError):
                core.index_document('../test.db')

if __name__ == '__main__':
    unittest.main()
