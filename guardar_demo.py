from datetime import date, datetime
from pathlib import Path

from assembly import AssemblyRequest, assemble_environmental_snapshot

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "demo"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

request = AssemblyRequest(
    lat=-12.471,
    lon=-76.790,
    target_date=date.today(),
)

snapshot = assemble_environmental_snapshot(request)
json_text = snapshot.to_json()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

filename = OUTPUT_DIR / f"snapshot_{timestamp}.json"

filename.write_text(
    json_text,
    encoding="utf-8"
)

print(f"Guardado en: {filename}")