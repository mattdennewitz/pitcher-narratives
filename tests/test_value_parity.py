from pitcher_narratives.value_parity import extract_metric_values


class TestExtractMetricValues:
    def test_grades_both_orders(self):
        v = extract_metric_values("a 130 Stuff+ pitch with S+ 112 and Location+ 97")
        assert ("grade", 130.0) in v
        assert ("grade", 112.0) in v
        assert ("grade", 97.0) in v

    def test_velocity(self):
        assert ("velo", 95.9) in extract_metric_values("sat 95.9 mph")

    def test_percent(self):
        assert ("pct", 25.0) in extract_metric_values("a 25.0% zone rate")

    def test_velo_and_pct_are_distinct_classes(self):
        v = extract_metric_values("81 mph fastball, 81% zone rate")
        assert ("velo", 81.0) in v
        assert ("pct", 81.0) in v  # same number, different class

    def test_xrv100_signed(self):
        v = extract_metric_values("xRV100 of -1.50 versus +0.32 xRV100")
        assert ("xrv100", -1.50) in v
        assert ("xrv100", 0.32) in v

    def test_percent_above_average_normalizes_to_grade(self):
        # "28% above average" == S+ 128
        assert ("grade", 128.0) in extract_metric_values("28% above average")

    def test_percent_below_average_normalizes_to_grade(self):
        assert ("grade", 87.0) in extract_metric_values("13% below average")

    def test_does_not_extract_word_numbers(self):
        # "two-seamer" must not yield a bogus value; no mph/%/grade context.
        assert extract_metric_values("his two-seamer and four-seamer") == set()
