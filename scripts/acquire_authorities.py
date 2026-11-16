"""Download public opinions listed in the manifest (those with a URL) into data/authorities/raw/
and print their hashes. Requires network; nothing else in Plus Factor does."""
import hashlib, json, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data"
out = ROOT / "authorities" / "raw"
out.mkdir(parents=True, exist_ok=True)
for a in json.loads((ROOT / "authority_manifest.json").read_text())["authorities"]:
    if not a["url"]:
        print(f"{a['id']}: no URL in manifest; acquire from the official reporter")
        continue
    data = urllib.request.urlopen(urllib.request.Request(a["url"], headers={"User-Agent": "plus-factor"}), timeout=60).read()
    (out / f"{a['id']}.pdf").write_bytes(data)
    print(f"{a['id']}: {len(data)} bytes sha256 {hashlib.sha256(data).hexdigest()}")
