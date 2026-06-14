run:
	uv run pitcher-narratives report -p 657277 -w 5

scout:
	uv run pitcher-scout -n 25 --min-score 5.0 -v

curate:
	uv run pitcher-scout -n 25 --min-score 5.0 --curate

# ── Data sync from Cloudflare R2 ──────────────────────────────────────
# Pulls the season parquet and the latest aggregate snapshot from the
# `pitchingplus` bucket to their expected local paths. Requires wrangler
# auth (`wrangler login`). Override the season with `make pull-data YEAR=2027`.
R2_BUCKET ?= pitchingplus
YEAR      ?= 2026
WRANGLER  ?= npx --yes wrangler@latest
# How many days back from today to look for the latest aggs snapshot.
AGGS_LOOKBACK ?= 14

.PHONY: pull-data pull-statcast pull-aggs

pull-data: pull-statcast pull-aggs

# statcast/<year>.parquet  <-  pitchingplus/statcast/<year>.parquet
pull-statcast:
	@mkdir -p statcast
	$(WRANGLER) r2 object get $(R2_BUCKET)/statcast/$(YEAR).parquet --remote --file statcast/$(YEAR).parquet

# aggs/  <-  pitchingplus/pitchingplus/aggs/<closest YYYY-MM-DD>/aggs.zip
# Snapshots are daily; walk back from today to the most recent one available,
# download the zip, unzip, and move the CSVs into aggs/.
pull-aggs:
	@mkdir -p aggs
	@tmp=$$(mktemp -d); \
	found=""; \
	for i in $$(seq 0 $(AGGS_LOOKBACK)); do \
		day=$$(date -v-$${i}d +%F 2>/dev/null || date -d "-$${i} days" +%F); \
		echo "Checking aggs snapshot $$day ..."; \
		if $(WRANGLER) r2 object get "$(R2_BUCKET)/pitchingplus/aggs/$$day/aggs.zip" \
			--remote --file "$$tmp/aggs.zip" >/dev/null 2>&1; then \
			found=$$day; break; \
		fi; \
	done; \
	if [ -z "$$found" ]; then \
		echo "No aggs snapshot found in the last $(AGGS_LOOKBACK) days." >&2; \
		rm -rf "$$tmp"; exit 1; \
	fi; \
	echo "Using aggs snapshot $$found"; \
	unzip -oq "$$tmp/aggs.zip" -d "$$tmp/unz"; \
	find "$$tmp/unz" -name '*.csv' -exec mv -f {} aggs/ \; ; \
	rm -rf "$$tmp"; \
	echo "Aggs refreshed into aggs/"
