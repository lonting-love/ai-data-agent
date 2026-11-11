import tempfile
import unittest
from pathlib import Path

import plot_chart_tool as chart_module
from plot_chart_tool import plot_chart_tool


class PlotChartToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_dir = chart_module.CHART_DIR
        chart_module.CHART_DIR = Path(self.tmp.name)

    def tearDown(self):
        chart_module.CHART_DIR = self.original_dir
        self.tmp.cleanup()

    def invoke(self, **kwargs) -> str:
        return plot_chart_tool.invoke(kwargs)

    def test_bar_chart_written_and_url_returned(self):
        result = self.invoke(x_data=["A", "B"], y_data=[1, 2], chart_type="柱状图", title="测试")
        self.assertIn("/charts/chart_", result)
        files = list(Path(self.tmp.name).glob("chart_*.html"))
        self.assertEqual(len(files), 1)

    def test_length_mismatch_rejected(self):
        result = self.invoke(x_data=["A"], y_data=[1, 2], chart_type="bar", title="x")
        self.assertIn("数量不一致", result)

    def test_unknown_chart_type_rejected(self):
        result = self.invoke(x_data=["A"], y_data=[1], chart_type="pie", title="x")
        self.assertIn("不支持的图表类型", result)

    def test_points_capped(self):
        result = self.invoke(
            x_data=[str(i) for i in range(80)],
            y_data=[float(i) for i in range(80)],
            chart_type="line",
            title="x",
        )
        self.assertIn("图表生成成功", result)


if __name__ == "__main__":
    unittest.main()
