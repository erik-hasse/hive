"""
Vehicle object for the HIVE platform
"""

import sys
import csv
import datetime
import numpy as np
import math
import os
import logging

from hive import helpers as hlp
from hive import tripenergy as nrg
from hive import charging as chrg
from hive import units
from hive.constraints import VEH_PARAMS
from hive.utils import assert_constraint, generate_csv_row


class Vehicle:
    """
    Base class for vehicle in mobility fleet.

    Parameters
    ----------
    veh_id: int
        Identifer assigned to vehicle object
    name: str
        Name of vehicle type.
    battery_capacity: float
        Battery capacity in kWh.
    max_charge_acceptance: float
        Maximum charge acceptace for the vehicle in kW.
    max_passengers: int
        Maximum number of passengers the vehicle can hold.
    whmi_lookup: pd.DataFrame
        Wh/mile lookup DataFrame
    charge_template: pd.DataFrame
        Charge template DataFrame
    clock: hive.utils.Clock
        simulation clock shared across the simulation to track simulation time steps.
    env_params: dict
        dictionary of all of the constant environment parameters shared across the simulation.
    """

    LOG_COLUMNS = [
                'ID',
                'sim_time',
                'time',
                'latitude',
                'longitude',
                'step_distance_mi',
                'active',
                'available',
                'reserve',
                'soc',
                'range_remaining',
                'activity',
                'station',
                'station_power',
                'base',
                'passengers',
                'reserve',
                ]

    def __init__(
                self,
                veh_id,
                name,
                battery_capacity,
                max_charge_acceptance,
                max_passengers,
                whmi_lookup,
                charge_template,
                clock,
                env_params,
                vehicle_log,
                ):

        # Public Constants
        self.ID = veh_id
        self.NAME = name
        assert_constraint(
                        'BATTERY_CAPACITY',
                        battery_capacity,
                        VEH_PARAMS,
                        context="Initialize Vehicle"
                        )
        self.BATTERY_CAPACITY = battery_capacity

        assert_constraint(
                        'MAX_CHARGE_ACCEPTANCE_KW',
                        max_charge_acceptance,
                        VEH_PARAMS,
                        context="Initialize Vehicle"
                        )
        self.MAX_CHARGE_ACCEPTANCE_KW = max_charge_acceptance

        assert_constraint(
                        'MAX_PASSENGERS',
                        max_passengers,
                        VEH_PARAMS,
                        context="Initialize Vehicle"
                        )
        self.MAX_PASSENGERS = max_passengers

        self.WH_PER_MILE_LOOKUP = whmi_lookup

        #TODO: Replace this with KWH__MI in fleet state
        self.AVG_WH_PER_MILE = np.mean(whmi_lookup['whmi'])

        self.CHARGE_TEMPLATE = charge_template

        # Public variables
        self.history = []

        # Postition variables
        self._lat = None
        self._lon = None

        self._route = None
        self._route_iter = None
        self._step_distance = 0

        self._station = None
        self._base = None

        self._idle_counter = 0

        self._clock = clock

        self.fleet_state = None

        self.activity = "Idle"

        self.ENV = env_params

        self.log = vehicle_log



    @property
    def lat(self):
        return self._lat

    @lat.setter
    def lat(self, val):
        self._lat = val
        self._set_fleet_state('lat', val)

    @property
    def lon(self):
        return self._lon

    @lon.setter
    def lon(self, val):
        self._lon = val
        self._set_fleet_state('lon', val)

    @property
    def active(self):
        col = self.ENV['FLEET_STATE_IDX']['active']
        return bool(self.fleet_state[self.ID, col])

    @active.setter
    def active(self, val):
        assert type(val) is bool, "This variable must be boolean"
        self._set_fleet_state('active', int(val))

    @property
    def available(self):
        col = self.ENV['FLEET_STATE_IDX']['available']
        return bool(self.fleet_state[self.ID, col])

    @available.setter
    def available(self, val):
        assert type(val) is bool, "This variable must be boolean"
        self._set_fleet_state('available', int(val))

    @property
    def soc(self):
        return self._get_fleet_state('soc')

    @soc.setter
    def soc(self, val):
        raise NotImplementedError('Please do not update soc directly. Use energy_kwh.')

    @property
    def energy_kwh(self):
        return self._energy_kwh

    @energy_kwh.setter
    def energy_kwh(self, val):
        soc = val / self.BATTERY_CAPACITY
        self._set_fleet_state('soc', soc)
        self._energy_kwh = val

    @property
    def idle_min(self):
        return self._get_fleet_state('idle_min')

    @available.setter
    def idle_min(self, val):
        self._set_fleet_state('idle_min', int(val))

    @property
    def avail_seats(self):
        return self._get_fleet_state('avail_seats')

    @avail_seats.setter
    def avail_seats(self, val):
        self._set_fleet_state('avail_seats', int(val))

    @property
    def range_remaining(self):
        range_miles = self.energy_kwh / self._get_fleet_state('KWH__MI')
        return range_miles

    @range_remaining.setter
    def range_remaining(self, val):
        raise NotImplementedError('Please do not set range_remaining directly. Use energy_kwh.')

    @property
    def charging(self):
        """
        This variable represents if a vehicle is charging. If the value is 0,
        the vehicle is not charging. If the value is greater than 0, the vehicle
        is charging with a power equal to the value of the charging variable.
        """
        return self._get_fleet_state('charging')

    @charging.setter
    def charging(self, val):
        self._set_fleet_state('charging', val)

    @property
    def reserve(self):
        col = self.ENV['FLEET_STATE_IDX']['reserve']
        return bool(self.fleet_state[self.ID, col])

    @reserve.setter
    def reserve(self, val):
        assert type(val) is bool, "This variable must be boolean"
        self._set_fleet_state('reserve', int(val))

    def __repr__(self):
        return str(f"Vehicle(id: {self.ID}, name: {self.NAME})")

    def _log(self):
        if self._station is None:
            station = None
        else:
            station = self._station.ID

        if self._base is None:
            base = None
        else:
            base = self._base.ID


        info = [
            ('ID', self.ID),
            ('sim_time', self._clock.now),
            ('time', self._clock.get_time()),
            ('latitude', self.lat),
            ('longitude', self.lon),
            ('step_distance_mi', self._step_distance),
            ('active', self.active),
            ('available', self.available),
            ('reserve', self.reserve),
            ('soc', self.soc),
            ('range_remaining', self.range_remaining),
            ('activity', self.activity),
            ('station', station),
            ('station_power', self.charging),
            ('base', base),
            ('passengers', self.MAX_PASSENGERS - self.avail_seats),
            ('reserve', self.reserve),
        ]

        self.log.info(generate_csv_row(info, self.LOG_COLUMNS))




    def _get_fleet_state(self, param):
        col = self.ENV['FLEET_STATE_IDX'][param]
        return self.fleet_state[self.ID, col]

    def _set_fleet_state(self, param, val):
        col = self.ENV['FLEET_STATE_IDX'][param]
        self.fleet_state[self.ID, col] = val

    def _update_charge(self, dist_mi):
        spd = self.ENV['DISPATCH_MPH']
        lookup = self.WH_PER_MILE_LOOKUP
        kwh__mi = (np.interp(spd, lookup['avg_spd_mph'], lookup['whmi']))/1000.0
        energy_used_kwh = dist_mi * kwh__mi
        self.energy_kwh -= energy_used_kwh

    def _leave_station(self):
        self._station.avail_plugs += 1
        self._station = None
        self.charging = 0

    def _update_idle(self):
        if self.activity == 'Idle':
            self._idle_counter += 1
            self.idle_min = self._idle_counter * self._clock.TIMESTEP_S * units.SECONDS_TO_MINUTES
        else:
            self._idle_counter = 0
            self.idle_min = 0

    def _move(self):
        if self._route is not None:
            try:
                location, dist_mi, activity = next(self._route_iter)
                self.activity = activity
                new_lat = location.lat
                new_lon = location.lon
                self._update_charge(dist_mi)
                self._step_distance = dist_mi
                self.lat = new_lat
                self.lon = new_lon
            except StopIteration:
                self._route = None
                if self._station is None:
                    self.available = True
                self.activity = "Idle"
                self.avail_seats = self.MAX_PASSENGERS
                self._step_distance = 0
        else:
            self._step_distance = 0

    def _charge(self):
        # Make sure we're not still traveling to charge station
        if self._route is None:
            self.activity = f"Charging at Station"
            energy_gained_kwh = self._station.dispense_energy()
            hyp_soc = (self._energy_kwh + energy_gained_kwh) / self.BATTERY_CAPACITY
            if hyp_soc <= self.ENV['UPPER_SOC_THRESH_STATION']:
                self.energy_kwh += energy_gained_kwh
            else:
                # Done charging,
                if self._base is None:
                    self.activity = "Idle"
                else:
                    self.activity = "Reserve"
                    self.reserve = True
                self.available = True
                self._leave_station()


    def cmd_make_trip(self, route, passengers):

        """
        Commands a vehicle to service a trip.

        Parameters
        ----------
        route: list
            list containing location, distnace and activity information representing
            a route.
        passengers: int
            the number of passengers associated with this trip.
        """
        if route is None:
            return

        start_lat = route[0][0].lat
        start_lon = route[0][0].lon

        assert (self.lat, self.lon) == (start_lat, start_lon), \
            "Route must start at current vehicle location"

        self.active = True
        self.available = False
        self.reserve = False
        self.avail_seats -= passengers
        self._base = None
        if self._station is not None:
            self._leave_station()

        self._route = route
        self._route_iter = iter(self._route)
        next(self._route_iter)

    def cmd_move(self, route):

        """
        Commands a vehicle to relocate to a new location.

        Parameters
        ----------
        route: list
            list containing location, distnace and activity information representing
            a route.
        """
        if route is None:
            return

        start_lat = route[0][0].lat
        start_lon = route[0][0].lon

        assert (self.lat, self.lon) == (start_lat, start_lon), \
            "Route must start at current vehicle location"

        self._route = route
        self._route_iter = iter(self._route)
        next(self._route_iter)

    def cmd_charge(self, station, route):
        """
        Commands the vehicle to charge at a station.

        Parameters
        ----------
        station: hive.stations.FuelStation
            station object for the vehicle to charge at.
        route: list
            list containing location, distance and activity information representing
            a route.
        """
        self.available = False
        self._station = station
        self._station.avail_plugs -= 1
        self.charging = station.PLUG_POWER_KW
        self.cmd_move(route)

    def cmd_unplug(self):
        """
        Commands to vehicle to unplug if currently charging.
        """
        if self._station and not self._route:
            self._leave_station()
            self.available = True
            if self._base:
                self.activity = "Reserve"
            else:
                self.activity = "Idle"


    def cmd_return_to_base(self, base, route):
        """
        Commands the vehicle to return to a base.

        Parameters
        ----------
        base: hive.stations.FuelStation
            base object for the vehicle to return to and charge at.
        route: list
            list containing location, distance and activity information representing
            a route.
        """
        self.available = True
        self.active = False
        self._base = base
        self._station = base
        self._station.avail_plugs -= 1
        self.charging = base.PLUG_POWER_KW
        self.cmd_move(route)


    def step(self):
        """
        Function is called for each simulation time step. Vehicle updates its state
        and performs and actions that have been assigned to it.
        """
        self._move()

        if self._station is not None:
            self._charge()

        self._update_idle()

        self._log()
