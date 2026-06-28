from pitcher_narratives.value_parity import check_value_parity, extract_metric_values


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

    def test_percent_vs_avg_without_space(self):
        # "13%below average" (no space) still normalizes to grade 87.
        assert ("grade", 87.0) in extract_metric_values("13%below average")

    def test_grade_label_does_not_grab_distant_number(self):
        # A number not immediately after the grade label (here a velocity) must
        # NOT be misclassified as a grade.
        v = extract_metric_values("his S+ sits 95 and he throws 95 mph")
        assert ("grade", 95.0) not in v
        assert ("velo", 95.0) in v

    def test_grade_with_of(self):
        assert ("grade", 130.0) in extract_metric_values("an S+ of 130 slider")


class TestCheckValueParity:
    def test_clean_when_all_values_trace_to_union(self):
        union = "Velocity 81.3 mph. S+ 130. zone 25.0%."
        capsule = "an 81 mph pitch grading 130 S+ in the zone 25% of the time"
        assert check_value_parity(capsule, union).is_clean

    def test_cross_class_collision_is_flagged(self):
        # capsule cites a 95 mph velo; union only has 95 as a percentage.
        union = "chase rate 95%"
        report = check_value_parity("sat 95 mph", union)
        assert not report.is_clean  # (velo,95) must NOT match (pct,95)

    def test_out_of_tolerance_grade_flagged(self):
        union = "S+ 130"
        assert not check_value_parity("a 124 S+ slider", "S+ 130").is_clean

    def test_within_tolerance_grade_clean(self):
        # whole-number grade tolerance is +/-1
        assert check_value_parity("a 131 S+ slider", "S+ 130").is_clean

    def test_paraphrase_grade_matches_pct_above_average(self):
        # capsule says "28% above average"; union has the grade 128.
        assert check_value_parity("28% above average", "S+ 128").is_clean

    def test_hedged_number_not_flagged(self):
        # "around 90" is hedged; even with no union support it is not flagged.
        assert check_value_parity("around 90 mph", "velocity 95.0 mph").is_clean

    def test_fabricated_value_flagged(self):
        report = check_value_parity("a 145 S+ monster", "S+ 130. velo 95 mph.")
        assert not report.is_clean
        assert any("145" in u for u in report.unmatched)

    def test_indeterminate_class_not_flagged(self):
        # a bare number with no metric context has no class -> never flagged.
        assert check_value_parity("he threw 17 pitches", "").is_clean

    def test_hedge_does_not_leak_across_class(self):
        # A hedged velocity (around 95 mph) must NOT suppress a fabricated grade
        # 95 elsewhere in the capsule. Union supports velo 95, not grade 95.
        capsule = "he sits around 95 mph and the slider grades 95 S+"
        report = check_value_parity(capsule, "velo 95 mph")
        assert not report.is_clean
        assert any("grade=95" in u for u in report.unmatched)
        # the hedged velo 95 itself is not flagged
        assert not any("velo=95" in u for u in report.unmatched)

    def test_negative_hedged_value_not_flagged(self):
        # "around -0.77 xRV100" is hedged; its sign must be preserved so the
        # suppression matches and no spurious advisory is emitted.
        assert check_value_parity("around -0.77 xRV100", "").is_clean
