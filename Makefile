run:
	uv run pitcher-narratives report -p 657277 -n 10

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

# var/statcast/<year>.parquet  <-  pitchingplus/statcast/<year>.parquet
# Downloads to a .part file and moves on success so an interrupted download
# never leaves a corrupt parquet in place.
pull-statcast:
	@mkdir -p var/statcast
	@set -e; \
	dest=var/statcast/$(YEAR).parquet; \
	rm -f "$$dest.part"; \
	$(WRANGLER) r2 object get $(R2_BUCKET)/statcast/$(YEAR).parquet --remote --file "$$dest.part"; \
	mv -f "$$dest.part" "$$dest"; \
	echo "Wrote $$dest"

# var/aggs/  <-  pitchingplus/pitchingplus/aggs/<closest YYYY-MM-DD>/aggs.zip
# Snapshots are daily; walk back from today to the most recent one available,
# download the zip, unzip, and move the CSVs into var/aggs/. `set -e` aborts on any
# download/unzip/move failure; the trap cleans up the temp dir on every exit.
pull-aggs:
	@mkdir -p var/aggs
	@set -e; \
	tmp=$$(mktemp -d); \
	trap 'rm -rf "$$tmp"' EXIT; \
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
		exit 1; \
	fi; \
	echo "Using aggs snapshot $$found"; \
	unzip -oq "$$tmp/aggs.zip" -d "$$tmp/unz"; \
	if [ -z "$$(find "$$tmp/unz" -name '*.csv' -print -quit)" ]; then \
		echo "aggs.zip contained no CSV files." >&2; exit 1; \
	fi; \
	find "$$tmp/unz" -name '*.csv' -exec mv -f {} var/aggs/ \; ; \
	echo "Aggs refreshed into var/aggs/"
