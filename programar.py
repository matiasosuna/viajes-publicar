"""Programa un video de viaje: lo sube al release "media" y lo anota en cola.json; GitHub lo publica a esa hora (nube.py).

Uso: python3 programar.py <video.mp4> <texto.txt> "2026-10-15 13:00" [--redes fb,yt,tk]  (IG lo publica él desde la app, con la traducción de Meta AI) [--titulo "título de YouTube"]
     [--red-cuando "ig=2026-10-18 13:00,fb=2026-10-18 13:00"] [--largo]   (--largo: YouTube como video normal, no Short)
La hora es de Hawái. El id sale del nombre del video ("2026-10-10 spitting-cave.mp4" → "2026-10-10-spitting-cave").
"""
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = "matiasosuna/viajes-publicar"
HST = datetime.timezone(datetime.timedelta(hours=-10))


def id_de(video):
    return re.sub(r"[^a-z0-9-]+", "-", Path(video).stem.lower()).strip("-")


def a_iso(cuando):
    return datetime.datetime.strptime(cuando, "%Y-%m-%d %H:%M").replace(tzinfo=HST).isoformat()


def armar_item(video, texto, cuando, redes=("fb", "yt", "tk"), titulo=None, cuando_red=None, largo=False):
    """cuando_red: {"ig": "2026-10-18 13:00"} para que una red salga otro día; largo: YouTube como video normal, no Short."""
    item = {"id": id_de(video), "cuando": a_iso(cuando), "texto": texto.strip(), "redes": list(redes)}
    if titulo:
        item["titulo_yt"] = titulo
    if cuando_red:
        item["cuando_red"] = {red: a_iso(h) for red, h in cuando_red.items()}
    if largo:
        item["shorts"] = False
    return item


def anotar(cola, item):
    """Reemplaza el del mismo id (reprogramar) y deja la cola ordenada por hora."""
    return sorted([i for i in cola if i["id"] != item["id"]] + [item], key=lambda i: i["cuando"])


def opcion(nombre):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else None


def main():
    video, texto, cuando = Path(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3]
    redes = (opcion("--redes") or "fb,yt,tk").split(",")
    cuando_red = dict(p.split("=", 1) for p in opcion("--red-cuando").split(",")) if opcion("--red-cuando") else None
    item = armar_item(video, texto, cuando, redes, opcion("--titulo"), cuando_red, "--largo" in sys.argv)
    if subprocess.run(["gh", "release", "view", "media", "-R", REPO], capture_output=True).returncode:
        subprocess.run(["gh", "release", "create", "media", "-R", REPO, "--title", "media",
                        "--notes", "Videos programados; se borran solos cuando ya salieron."], check=True)
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / f"{item['id']}.mp4"
        shutil.copyfile(video, copia)
        subprocess.run(["gh", "release", "upload", "media", str(copia), "--clobber", "-R", REPO], check=True)
    subprocess.run(["git", "-C", str(AQUI), "pull", "--rebase", "-q"], check=True)
    cola_json = AQUI / "cola.json"
    cola_json.write_text(json.dumps(anotar(json.loads(cola_json.read_text()), item), ensure_ascii=False, indent=1) + "\n")
    subprocess.run(["git", "-C", str(AQUI), "add", "cola.json"], check=True)
    subprocess.run(["git", "-C", str(AQUI), "commit", "-qm", f"programar {item['id']} {cuando}"], check=True)
    subprocess.run(["git", "-C", str(AQUI), "push", "-q"], check=True)
    print(f"programado {item['id']}: {cuando} HST en {', '.join(redes)}")


if __name__ == "__main__":
    main()
