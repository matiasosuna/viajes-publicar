import datetime
import unittest

import nube
import programar

HST = datetime.timezone(datetime.timedelta(hours=-10))


class TestNube(unittest.TestCase):
    def test_pendientes_por_hora_redes_y_claves(self):
        cola = [{"id": "a", "cuando": "2026-10-15T13:00:00-10:00", "redes": ["ig", "yt"], "hecho": {"ig": "x"}},
                {"id": "b", "cuando": "2026-10-16T13:00:00-10:00", "redes": ["ig"]}]
        antes = datetime.datetime(2026, 10, 15, 12, 40, tzinfo=HST)
        casi = datetime.datetime(2026, 10, 15, 12, 52, tzinfo=HST)
        self.assertEqual(nube.pendientes(cola, antes, {"ig", "yt"}), [])
        self.assertEqual([(i["id"], r) for i, r in nube.pendientes(cola, casi, {"ig", "yt"})], [("a", "yt")])
        self.assertEqual(nube.pendientes(cola, casi, {"ig"}), [])  # YouTube sin claves: espera

    def test_terminados_y_titulo(self):
        cola = [{"id": "a", "redes": ["ig"], "hecho": {"ig": "x"}}, {"id": "b", "redes": ["ig", "yt"], "hecho": {"ig": "x"}},
                {"id": "c", "redes": ["ig"], "hecho": {"ig": "x"}, "borrado": True}]
        self.assertEqual([i["id"] for i in nube.terminados(cola)], ["a"])
        self.assertEqual(nube.datos_youtube("Atardecer 🌅\n\n#oahu")["snippet"]["title"], "Atardecer 🌅 #Shorts")

    def test_programar_item_y_cola(self):
        item = programar.armar_item("salidas/dias/2026-10-10 spitting-cave.mp4", "Atardecer 🌅\n", "2026-10-15 13:00", ["ig"])
        self.assertEqual(item, {"id": "2026-10-10-spitting-cave", "cuando": "2026-10-15T13:00:00-10:00",
                                "texto": "Atardecer 🌅", "redes": ["ig"]})
        viejo = dict(item, cuando="2026-10-14T13:00:00-10:00")
        otro = {"id": "x", "cuando": "2026-10-15T06:00:00-10:00"}
        self.assertEqual(programar.anotar([viejo, otro], item), [otro, item])  # reprogramado, sin duplicar


if __name__ == "__main__":
    unittest.main()
