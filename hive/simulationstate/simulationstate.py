from __future__ import annotations
from copy import copy
from typing import NamedTuple, Dict, Optional, Union, Tuple

from hive.model.base import Base
from hive.model.request import Request
from hive.model.station import Station
from hive.model.vehicle import Vehicle
from hive.roadnetwork.roadnetwork import RoadNetwork
from hive.util.typealiases import *
from hive.util.exception import *
from h3 import h3


class SimulationState(NamedTuple):
    # model data required in constructor
    road_network: RoadNetwork
    stations: Dict[StationId, Station]
    bases: Dict[BaseId, Base]
    s_locations: Dict[GeoId, StationId] = {}
    b_locations: Dict[GeoId, Base] = {}

    # model data with default as empty
    vehicles: Dict[VehicleId, Vehicle] = {}
    requests: Dict[RequestId, Request] = {}

    # location lookup collections
    v_locations: Dict[GeoId, VehicleId] = {}
    r_locations: Dict[GeoId, RequestId] = {}

    # todo: a constructor which doesn't expect s + b locations

    # resolution of 11 is within 25 meters/82 feet. this decides how granular
    # the simulation will operate for internal operations. the user can still
    # specify their own level of granularity for
    # https://uber.github.io/h3/#/documentation/core-library/resolution-table
    sim_h3_resolution: int = 11
    cluster_node_id: Optional[ClusterNodeId] = None

    def add_request(self, request: Request) -> Union[SimulationStateError, SimulationState]:
        """
        adds a request to the SimulationState
        :param request: the request to add
        :return: the updated simulation state, or an error
        """
        if not self.road_network.coordinate_within_geofence(request.origin):
            return SimulationStateError(f"origin {request.origin} not within road network geofence of this")
        elif not self.road_network.coordinate_within_simulation(request.destination):
            return SimulationStateError(f"destination {request.destination} not within entire road network")
        else:
            request_geoid = h3.geo_to_h3(request.origin.lat, request.origin.lon, self.sim_h3_resolution)
            # TODO: should we do this? push the request to the center of the h3 hex?
            #  that way, given the correct spatial resolution, we should always have
            #  a buffer to overlap vehicles to requests which is equal to the radius
            #  of the spatial resolution?
            geoid_centroid = h3.h3_to_geo(request_geoid)
            new_lat, new_lon = (geoid_centroid[0], geoid_centroid[1])
            updated_request = request.update_origin(new_lat, new_lon)

            updated_requests = copy(self.requests)
            updated_requests.update((updated_request.id, updated_request))

            updated_r_locations = copy(self.r_locations)
            updated_r_locations.update((request_geoid, updated_request.id))

            return self._replace(
                requests=updated_requests,
                r_locations=updated_r_locations
            )

    def remove_request(self, request_id: RequestId) -> SimulationState:
        """
        removes a request from this simulation.
        called once a Request has been fully serviced and is no longer
        alive in the simulation.
        :param request_id: id of the request to delete
        :return: the updated simulation state (does not report failure)
        """
        if request_id not in self.requests:
            return self
        else:
            request = self.requests[request_id]
            request_geoid = h3.geo_to_h3(request.origin.lat, request.origin.lon, self.sim_h3_resolution)

            updated_requests = copy(self.requests)
            del updated_requests[request_id]

            updated_r_locations = copy(self.r_locations)
            del updated_r_locations[request_geoid]

            return self._replace(
                requests=updated_requests,
                r_locations=updated_r_locations
            )

    def add_vehicle(self, vehicle: Vehicle) -> SimulationState:
        """
        adds a vehicle into the region supported by the RoadNetwork in this SimulationState
        :param vehicle: a vehicle
        :return: updated SimulationState
        """
        pass

    def remove_vehicle(self, vehicle_id: VehicleId) -> SimulationState:
        """
        removes the vehicle from play (perhaps to simulate a broken vehicle or end of a shift)
        :param vehicle_id: the id of the vehicle
        :return: the updated simulation state
        """
        pass

    def pop_vehicle(self, vehicle_id: VehicleId) -> Union[SimulationStateError, Tuple[SimulationState, Vehicle]]:
        """
        removes a vehicle from this SimulationState, which updates the state and also returns the vehicle
        :param vehicle_id: the id of the vehicle to pop
        :return: either a Tuple containing the updated state and the vehicle, or, an error
        """
        pass

    def update_road_network(self, sim_time: int) -> SimulationState:
        """
        trigger the update of the road network model based on the current sim time
        :param sim_time: the current sim time
        :return: updated simulation state (and road network)
        """
        return self._replace(
            road_network=self.road_network.update(sim_time)
        )

    def board_vehicle(self,
                      request_id: RequestId,
                      vehicle_id: VehicleId) -> Union[SimulationStateError, SimulationState]:
        """
        places passengers from a request into a Vehicle
        :param request_id:
        :param vehicle_id:
        :return: updated simulation state, or an error
        """
        if vehicle_id not in self.vehicles:
            return SimulationStateError(
                f"request {request_id} attempting to board vehicle {vehicle_id} which does not exist")
        elif request_id not in self.requests:
            return SimulationStateError(
                f"request {request_id} does not exist but is attempting to board vehicle {vehicle_id}")
        else:
            vehicle = self.vehicles[vehicle_id]
            request = self.requests[request_id]
            updated_vehicle = vehicle.add_passengers(request.passengers)

            updated_vehicles = copy(self.vehicles)
            updated_vehicles.update((vehicle_id, updated_vehicle))

            # todo: hey, maybe it's weird in the distributed case to "leave behind" the request
            #  after the passengers have boarded. how helpful is it to have the old cluster node
            #  still holding this info, and, what would it take to tell it to remove the old
            #  request when we deliver a passenger in another cluster node?
            # maybe it should just go live somewhere else after it's been instantiated as passengers,
            # or maybe even just deleted, if it has no further use. programmatically, i don't think
            # it will serve a purpose to keep it alive. life beyond a sim step isn't really managed
            # at this level either. maybe the SimulationRunner would keep track of the full lifespan
            # of a request/passenger and the sim doesn't need to track that (i.e., deletes the Request
            # here instead). 20191111-rjf

            return self._replace(
                vehicles=updated_vehicles
            )

    def vehicle_at_request(self,
                           vehicle_id: VehicleId,
                           request_id: RequestId,
                           override_resolution: Optional[int]) -> bool:
        """
        tests whether vehicle is at the request within the scope of the given geoid resolution
        :param vehicle_id: the vehicle we are testing for proximity to a request
        :param request_id: the request we are testing for proximity to a vehicle
        :param override_resolution: a resolution to use for geo intersection test; if None, use self.sim_h3_resolution
        :return: bool
        """
        if vehicle_id not in self.vehicles or request_id not in self.requests:
            return False
        else:
            vehicle = self.vehicles[vehicle_id]
            request = self.requests[request_id]

            test_resolution = override_resolution if override_resolution is not None else self.sim_h3_resolution
            vehicle_coordinate = self.road_network.position_to_coordinate(vehicle.position)

            vehicle_geoid = h3.geo_to_h3(vehicle_coordinate.lat, vehicle_coordinate.lon, test_resolution)
            request_geoid = h3.geo_to_h3(request.origin.lat, request.origin.lon, test_resolution)

            return vehicle_geoid == request_geoid

    def get_vehicle_geoid(self, vehicle_id) -> Optional[GeoId]:
        """
        updates the geoid of a vehicle based on the vehicle's coordinate
        :param vehicle_id: id of the vehicle from which we want a geoid
        :return: a geoid, or nothing if the vehicle doesn't exist
        """
        if vehicle_id not in self.vehicles:
            return None
        else:
            vehicle_position = self.vehicles[vehicle_id].position
            vehicle_coordinate = self.road_network.position_to_coordinate(vehicle_position)
            new_geoid = h3.geo_to_h3(vehicle_coordinate.lat, vehicle_coordinate.lon, self.sim_h3_resolution)
            return new_geoid

    def assign_cluster_node_id(self, cluster_node_id: ClusterNodeId) -> SimulationState:
        return self._replace(cluster_node_id=cluster_node_id)
