"""Publica solo, desde GitHub Actions (cada hora), los videos de viaje programados en cola.json. Como Myths on Clay:
la Mac puede estar apagada.

cola.json: [{"id": "2026-10-10-spitting-cave", "cuando": "2026-10-15T13:00:00-10:00", "texto": "…",
             "redes": ["ig", "fb", "yt", "tk"], "hecho": {"ig": "https://…"}}]
El video es el asset <id>.mp4 del release "media" de este repo; cuando ya salió en todas sus redes, el asset se borra.
Claves (secretos del repo, nunca se imprimen):
  ig/fb: META_PAGE_TOKEN, IG_USER_ID, META_PAGE_ID · yt: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  tk (TikTok por Buffer, como Myths): BUFFER_API_KEY, BUFFER_TIKTOK_CANAL
Una red sin sus claves queda pendiente (no falla) y sale en la primera corrida después de cargarlas.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "matiasosuna/viajes-publicar")
COLA = Path(__file__).with_name("cola.json")
GRAPH = "https://graph.facebook.com/v23.0"
ANTES = datetime.timedelta(minutes=2)  # margen: lo que vence en 2 min ya sale
CLAVES = {"ig": ("META_PAGE_TOKEN", "IG_USER_ID"), "fb": ("META_PAGE_TOKEN", "META_PAGE_ID"),
          "yt": ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"), "tk": ("BUFFER_API_KEY", "BUFFER_TIKTOK_CANAL")}


def url_video(item):
    return f"https://github.com/{REPO}/releases/download/media/{item['id']}.mp4"


def pedir(url, datos=None, cabeceras=None, metodo=None, cuerpo=None, timeout=600):
    if datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode()
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras or {}, method=metodo or ("POST" if cuerpo is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code}: {e.read().decode()[:400]}") from None


def instagram(item, e):
    token, ig = e["META_PAGE_TOKEN"], e["IG_USER_ID"]
    cont, _ = pedir(f"{GRAPH}/{ig}/media", {"media_type": "REELS", "video_url": url_video(item), "caption": item["texto"],
                                            "share_to_feed": "true", "access_token": token})
    for _ in range(120):  # Instagram baja y procesa el video: hasta ~10 min
        estado, _ = pedir(f"{GRAPH}/{cont['id']}?fields=status_code,status&access_token={token}")
        if estado.get("status_code") == "FINISHED":
            break
        if estado.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram no pudo procesar el video: {estado.get('status')}")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram tardó demasiado en procesar el video")
    media, _ = pedir(f"{GRAPH}/{ig}/media_publish", {"creation_id": cont["id"], "access_token": token})
    try:
        return pedir(f"{GRAPH}/{media['id']}?fields=permalink&access_token={token}")[0]["permalink"]
    except Exception:
        return f"publicado (media {media['id']})"  # ya salió: nunca reintentar


def facebook(item, e):
    """Reel en la página: Facebook baja el video del link (file_url), sin subir el archivo."""
    token, pagina = e["META_PAGE_TOKEN"], e["META_PAGE_ID"]
    ini, _ = pedir(f"{GRAPH}/{pagina}/video_reels", {"upload_phase": "start", "access_token": token})
    pedir(f"https://rupload.facebook.com/video-upload/v23.0/{ini['video_id']}", metodo="POST", cuerpo=b"",
          cabeceras={"Authorization": f"OAuth {token}", "file_url": url_video(item)})
    pedir(f"{GRAPH}/{pagina}/video_reels", {"upload_phase": "finish", "video_id": ini["video_id"], "video_state": "PUBLISHED",
                                            "description": item["texto"], "access_token": token})
    return f"https://www.facebook.com/reel/{ini['video_id']}"


def datos_youtube(texto, titulo=None):
    """Título (máx. 100, con #Shorts) y descripción del Short."""
    titulo = (titulo or texto.strip().splitlines()[0]).strip()
    if "#shorts" not in titulo.lower():
        titulo = f"{titulo[:100 - 8].rstrip()} #Shorts"
    return {"snippet": {"title": titulo[:100], "description": texto, "categoryId": "19",  # Viajes y eventos
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}


def youtube(item, e):
    token = pedir("https://oauth2.googleapis.com/token", {"client_id": e["YT_CLIENT_ID"], "client_secret": e["YT_CLIENT_SECRET"],
                                                          "refresh_token": e["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})[0]["access_token"]
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "video.mp4"
        urllib.request.urlretrieve(url_video(item), video)
        _, cab = pedir("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                       cuerpo=json.dumps(datos_youtube(item["texto"], item.get("titulo_yt"))).encode(), metodo="POST", cabeceras={
                           "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                           "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(video.stat().st_size)})
        hecho, _ = pedir(cab["Location"], cuerpo=video.read_bytes(), metodo="PUT", timeout=1800,
                         cabeceras={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    estado = hecho.get("status", {}).get("privacyStatus")
    return f"https://youtube.com/shorts/{hecho['id']}" + ("" if estado == "public" else f" (quedó {estado})")


def tiktok(item, e):
    """Por Buffer, como Myths on Clay: sale ya, con el video tomado del link."""
    mutacion = ("mutation { createPost(input: { text: %s, channelId: %s, schedulingType: automatic, mode: shareNow, "
                "assets: [{ video: { url: %s } }] }) { ... on PostActionSuccess { post { id } } ... on MutationError { message } } }"
                % (json.dumps(item["texto"]), json.dumps(e["BUFFER_TIKTOK_CANAL"]), json.dumps(url_video(item))))
    r, _ = pedir("https://api.buffer.com", cuerpo=json.dumps({"query": mutacion}).encode(), metodo="POST",
                 cabeceras={"Authorization": f"Bearer {e['BUFFER_API_KEY']}", "Content-Type": "application/json"})
    if r.get("errors") or "message" in r["data"]["createPost"]:
        raise RuntimeError(json.dumps(r.get("errors") or r["data"]["createPost"])[:300])
    return f"buffer {r['data']['createPost']['post']['id']}"


def toca(item, ahora):
    return datetime.datetime.fromisoformat(item["cuando"]) - ANTES <= ahora


def pendientes(cola, ahora, hay):
    """[(item, red)] que ya tocan, no salieron y tienen sus claves."""
    return [(item, red) for item in cola if toca(item, ahora)
            for red in item["redes"] if red not in item.get("hecho", {}) and red in hay]


def espera(cola, ahora, hay, hasta=datetime.timedelta(minutes=70)):
    """Segundos hasta lo próximo que vence en la próxima hora (0 si no hay): la corrida espera y sale a la hora justa,
    porque GitHub atrasa el cron hasta ~50 min."""
    proximos = [datetime.datetime.fromisoformat(item["cuando"]) - ANTES for item in cola
                if any(r not in item.get("hecho", {}) and r in hay for r in item["redes"])]
    proximos = [p for p in proximos if ahora < p <= ahora + hasta]
    return (min(proximos) - ahora).total_seconds() if proximos else 0


def terminados(cola):
    return [item for item in cola if not item.get("borrado") and all(r in item.get("hecho", {}) for r in item["redes"])]


def main():
    e = os.environ
    hay = {red for red, claves in CLAVES.items() if all(e.get(k) for k in claves)}
    cola = json.loads(COLA.read_text())
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if segundos := espera(cola, ahora, hay):
        print(f"espero {segundos / 60:.0f} min a la hora programada", flush=True)
        time.sleep(segundos)
        ahora = datetime.datetime.now(datetime.timezone.utc)
    falla = False
    for item, red in pendientes(cola, ahora, hay):
        try:
            link = {"ig": instagram, "fb": facebook, "yt": youtube, "tk": tiktok}[red](item, e)
            item.setdefault("hecho", {})[red] = link
            item.get("errores", {}).pop(red, None)
            print(f"{item['id']} {red}: {link}", flush=True)
        except Exception as error:
            falla = True
            item.setdefault("errores", {})[red] = str(error)[:300]
            print(f"{item['id']} {red}: NO se pudo — {str(error)[:300]}", flush=True)
        COLA.write_text(json.dumps(cola, ensure_ascii=False, indent=1) + "\n")  # después de cada red, por si se corta
    for item in terminados(cola):  # ya salió en todo: el video deja de estar en el release
        subprocess.run(["gh", "release", "delete-asset", "media", f"{item['id']}.mp4", "-y", "-R", REPO], check=False)
        item["borrado"] = True
    COLA.write_text(json.dumps(cola, ensure_ascii=False, indent=1) + "\n")
    faltan = sorted({red for item in cola for red in item["redes"] if red not in item.get("hecho", {})} - hay)
    if faltan:
        print(f"sin claves todavía: {', '.join(faltan)} (queda pendiente)")
    sys.exit(1 if falla else 0)


if __name__ == "__main__":
    main()
