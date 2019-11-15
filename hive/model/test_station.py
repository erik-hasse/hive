from unittest import TestCase, skip

from h3 import h3

from hive.model.coordinate import Coordinate
from hive.model.station import Station
from hive.model.charger import Charger, ChargerType


class TestStation(TestCase):
    _mock_l2_charger = Charger("charger1",
                               ChargerType.LEVEL_2,
                               7.2,
                               )
    _mock_dcfc_charger = Charger("charger2",
                                 ChargerType.DCFC,
                                 50,
                                 )
    _mock_station = Station("test_station",
                            Coordinate(0, 0),
                            h3.geo_to_h3(0, 0, 11),
                            {_mock_l2_charger.id: _mock_l2_charger, _mock_dcfc_charger.id: _mock_dcfc_charger},
                            )

    def test_checkout_charger(self):
        updated_station, dcfc_charger = self._mock_station.checkout_charger(ChargerType.DCFC, "test_vehicle")

        self.assertEqual(dcfc_charger.in_use, True)
        self.assertEqual(dcfc_charger.type, ChargerType.DCFC)

    def test_checkout_charger_none_avail(self):
        updated_station, dcfc_charger = self._mock_station.checkout_charger(ChargerType.DCFC, "test_vehicle")

        no_dcfc_station, no_dcfc_charger = updated_station.checkout_charger(ChargerType.DCFC, "test_vehicle")

        self.assertIsNone(no_dcfc_charger)

    def test_return_charger(self):
        updated_station, l2_charger = self._mock_station.checkout_charger(ChargerType.LEVEL_2, "test_vehicle")

        station_w_l2 = updated_station.return_charger(l2_charger.id)

        self.assertEqual(station_w_l2.chargers[l2_charger.id].in_use, False)



