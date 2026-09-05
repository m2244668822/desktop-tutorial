import gc
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from core.memory_layers import ThreeLayerMemory


class ThreeLayerMemoryConnectionTests(unittest.TestCase):
    def test_sqlite_connections_are_closed_after_operations(self):
        with tempfile.TemporaryDirectory() as workspace:
            with patch.dict(
                "os.environ", {"TREVOR_DATA_DIR": str(Path(workspace) / "data")}
            ), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)

                memory = ThreeLayerMemory(workspace)
                memory.stats()
                memory.search("hello", top_k=1)
                del memory
                gc.collect()

            unclosed = [
                warning
                for warning in caught
                if issubclass(warning.category, ResourceWarning)
                and "unclosed database" in str(warning.message)
            ]
            self.assertEqual([], unclosed)


if __name__ == "__main__":
    unittest.main()
