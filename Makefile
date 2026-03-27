run:
	uv run pitcher-narratives -p 657277 -w 5

scout:
	uv run pitcher-scout -n 25 --min-score 5.0 -v

curate:
	uv run pitcher-scout -n 25 --min-score 5.0 --curate
