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
        casi = datetime.datetime(2026, 10, 15, 12, 59, tzinfo=HST)
        self.assertEqual(nube.pendientes(cola, antes, {"ig", "yt"}), [])
        self.assertEqual([(i["id"], r) for i, r in nube.pendientes(cola, casi, {"ig", "yt"})], [("a", "yt")])
        self.assertEqual(nube.pendientes(cola, casi, {"ig"}), [])  # YouTube sin claves: espera

    def test_espera_a_la_hora_justa(self):
        cola = [{"id": "a", "cuando": "2026-10-15T13:00:00-10:00", "redes": ["ig"]}]
        corrida = datetime.datetime(2026, 10, 15, 12, 25, tzinfo=HST)  # el cron de :20 llegó 5 min tarde
        self.assertEqual(nube.espera(cola, corrida, {"ig"}), 33 * 60)  # hasta las 12:58 (margen de 2 min)
        self.assertEqual(nube.espera(cola, corrida - datetime.timedelta(hours=2), {"ig"}), 0)  # falta mucho
        self.assertEqual(nube.espera(cola, corrida, {"yt"}), 0)  # nada de lo que vence tiene claves
        hecho = [dict(cola[0], hecho={"ig": "x"})]
        self.assertEqual(nube.espera(hecho, corrida, {"ig"}), 0)

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

    def test_cada_red_con_su_hora_y_youtube_largo(self):
        item = programar.armar_item("a.mp4", "Maui 🌅\n", "2026-10-17 13:00", ["yt", "ig"], cuando_red={"ig": "2026-10-19 13:00"},
                                    largo=True)
        sabado = datetime.datetime(2026, 10, 17, 13, 0, tzinfo=HST)
        self.assertEqual([r for _, r in nube.pendientes([item], sabado, {"yt", "ig"})], ["yt"])  # IG espera al lunes
        self.assertEqual(nube.espera([dict(item, hecho={"yt": "x"})], datetime.datetime(2026, 10, 19, 12, 30, tzinfo=HST),
                                     {"ig"}), 28 * 60)
        self.assertEqual(nube.datos_youtube(item["texto"], shorts=item["shorts"])["snippet"]["title"], "Maui 🌅")


if __name__ == "__main__":
    unittest.main()
