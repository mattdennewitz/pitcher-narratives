run:
	uv run pitcher-narratives report -p 657277 -n 10

scout:
	uv run pitcher-narratives scoreboard -n 25 --min-score 5.0 --format table -v

curate:
	uv run pitcher-narratives scoreboard -n 25 --min-score 5.0 --curate

# ── PitchingPlus bundle sync from Cloudflare R2 ──────────────────────
# Pulls the latest producer-owned, manifest-covered output bundle. Raw
# Statcast is a PitchingPlus input and is never installed in this repository.
R2_BUCKET ?= pitchingplus
WRANGLER  ?= npx --yes wrangler@latest
AGGS_LOOKBACK ?= 14
PITCHINGPLUS_DIR ?= ../pitchingplus

.PHONY: pull-data release-acceptance
release-acceptance:
	uv run pytest -q \
		tests/test_analysis_integrity_acceptance.py \
		tests/test_consumer_claim_repairs.py \
		tests/test_claim_capabilities.py \
		tests/test_hallucination_guard.py \
		tests/test_model_explainer.py \
		tests/test_frame_delta.py
	uv run pytest -q tests/test_data.py \
		-k 'semantic or calibration or attribution or manifest_registry or producer_identity or with_frame or historical_as_of or exact_latest or missing_current_attribution or registered_attribution or required_grain or formal_l' \
		tests/test_attribution.py tests/test_calibration.py tests/test_facts.py
	cd "$(PITCHINGPLUS_DIR)" && uv run pytest -p no:django -q \
		packages/plus/tests/test_output_bundle.py \
		packages/plus/tests/test_export.py \
		packages/plus/tests/evaluation/test_evaluate_command.py \
		packages/plus/tests/prediction/test_metric_semantics.py \
		packages/plus/tests/prediction/test_outcome_attribution.py \
		packages/plus/tests/pipeline/test_output_structure.py \
		packages/plus/tests/golden/test_aggregations.py \
		packages/plus/tests/golden/test_columns.py \
		packages/plus/tests/pipeline/test_aggregation_counts.py \
		packages/plus-schemas/tests


pull-data:
	@set -e; \
	mkdir -p var; \
	tmp=$$(mktemp -d); \
	stage="var/.aggs-stage-$$$$"; \
	previous="var/.aggs-previous-$$$$"; \
	cleanup() { status=$$?; trap - EXIT; rm -rf "$$tmp" "$$stage"; if [ $$status -ne 0 ] && [ ! -e var/aggs ] && [ -e "$$previous" ]; then mv "$$previous" var/aggs; fi; if [ $$status -eq 0 ]; then rm -rf "$$previous"; fi; exit $$status; }; \
	trap cleanup EXIT; \
	found=""; \
	for i in $$(seq 0 $(AGGS_LOOKBACK)); do \
		day=$$(date -v-$${i}d +%F 2>/dev/null || date -d "-$${i} days" +%F); \
		echo "Checking PitchingPlus bundle $$day ..."; \
		if $(WRANGLER) r2 object get "$(R2_BUCKET)/pitchingplus/aggs/$$day/aggs.zip" \
			--remote --file "$$tmp/bundle.zip" >/dev/null 2>&1; then \
			found=$$day; break; \
		fi; \
	done; \
	if [ -z "$$found" ]; then \
		echo "No PitchingPlus bundle found in the last $(AGGS_LOOKBACK) days." >&2; \
		exit 1; \
	fi; \
	echo "Using PitchingPlus bundle $$found"; \
	unzip -oq "$$tmp/bundle.zip" -d "$$tmp/bundle"; \
	uv run python -c 'import sys; from pathlib import Path; from pitcher_narratives.data import load_pitchingplus_bundle; root = Path(sys.argv[1]); seasons = tuple(sorted(int(path.name.split("-", 1)[0]) for path in root.glob("*-metric-semantics.json"))); assert seasons, "bundle is missing its metric-semantics manifest"; load_pitchingplus_bundle(root, seasons=seasons)' "$$tmp/bundle"; \
	mkdir -p "$$stage"; \
	if [ -d var/aggs ]; then cp -R var/aggs/. "$$stage/"; fi; \
	for manifest in "$$tmp/bundle/"*-metric-semantics.json; do \
		season=$${manifest##*/}; season=$${season%%-*}; \
		rm -f "$$stage/$$season-"*; \
	done; \
	cp -R "$$tmp/bundle/." "$$stage/"; \
	uv run python -c 'import sys; from pathlib import Path; from pitcher_narratives.data import load_pitchingplus_bundle; load_pitchingplus_bundle(Path(sys.argv[1]))' "$$stage"; \
	if [ -e var/aggs ] || [ -L var/aggs ]; then mv var/aggs "$$previous"; fi; \
	mv "$$stage" var/aggs; \
	echo "PitchingPlus bundle installed in var/aggs/"
