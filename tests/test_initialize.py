import unittest
import pandas as pd
import os

from hive.initialize import initialize_charge_network, initialize_fleet
from hive.station import FuelStation
from hive.vehicle import Vehicle

TEST_INPUT_DIR = os.path.join('inputs', '.inputs_default')

class InitializeChargeNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.CHARGE_NET_FILE = os.path.join(TEST_INPUT_DIR,
                                        'charge_network',
                                        'aus_fuel_stations.csv')

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_initialize_charging_network_stations(self):
        charge_net_df = pd.read_csv(self.CHARGE_NET_FILE)
        stations, depots = initialize_charge_network(charge_net_df,
                                            station_log_file='placeholder.csv')
        self.assertEqual(len(stations), 186)

    def test_initialize_charging_network_depots(self):
        charge_net_df = pd.read_csv(self.CHARGE_NET_FILE)
        stations, depots = initialize_charge_network(charge_net_df,
                                            station_log_file='placeholder.csv')
        self.assertEqual(len(depots), 2)

    def test_initialize_charging_network_type(self):
        charge_net_df = pd.read_csv(self.CHARGE_NET_FILE)
        stations, depots = initialize_charge_network(charge_net_df,
                                            station_log_file='placeholder.csv')
        self.assertIsInstance(stations[0], FuelStation)


class InitializeFleetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.CHARGE_NET_FILE = os.path.join(TEST_INPUT_DIR,
                                        'charge_network',
                                        'aus_fuel_stations.csv')
        cls.CHARGE_CURVE_FILE = os.path.join(TEST_INPUT_DIR,
                                            '.lib',
                                            'raw_leaf_curves.csv')
        cls.WHMI_LOOKUP_FILE = os.path.join(TEST_INPUT_DIR,
                                            '.lib',
                                            'wh_mi_lookup.csv')
        cls.FLEET_FILE = os.path.join(TEST_INPUT_DIR,
                                            'fleets',
                                            'aus_fleet.csv')


    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        fleet_df = pd.read_csv(self.FLEET_FILE)
        charge_net_df = pd.read_csv(self.CHARGE_NET_FILE)
        _, depots = initialize_charge_network(charge_net_df,
                                            station_log_file='placeholder.csv')
        self.depots = depots
        self.charge_curve_df = pd.read_csv(self.CHARGE_CURVE_FILE)
        self.whmi_df = pd.read_csv(self.WHMI_LOOKUP_FILE)
        self.vehicles = list()
        for i, veh in fleet_df.iterrows():
            veh_file = os.path.join(TEST_INPUT_DIR, 'vehicles', '{}.csv'.format(veh.VEHICLE_NAME))
            veh_df = pd.read_csv(veh_file)
            veh_df['VEHICLE_NAME'] = veh.VEHICLE_NAME
            veh_df['NUM_VEHICLES'] = veh.NUM_VEHICLES
            self.vehicles.append(veh_df.iloc[0])
        self.env_params = {
            'MAX_DISPATCH_MILES': 5,
            'MIN_ALLOWED_SOC': 20,
            'RN_SCALING_FACTOR': 2,
            'DISPATCH_MPH': 30,
        }

    def tearDown(self):
        pass

    def test_initialize_fleet_size(self):
        fleet = initialize_fleet(self.vehicles,
                                    self.depots,
                                    self.charge_curve_df,
                                    self.whmi_df,
                                    self.env_params,
                                    vehicle_log_file = "placeholder.csv",)
        self.assertEqual(len(fleet), 130)

    def test_initialize_fleet_type(self):
        fleet = initialize_fleet(self.vehicles[0:1],
                                    self.depots,
                                    self.charge_curve_df,
                                    self.whmi_df,
                                    self.env_params,
                                    vehicle_log_file = "placeholder.csv",)
        self.assertIsInstance(fleet[0], Vehicle)




if __name__ == '__main__':
    unittest.main()
