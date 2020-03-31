from __future__ import annotations

from typing import Tuple, NamedTuple, TYPE_CHECKING

from hive.util.units import Ratio

if TYPE_CHECKING:
    from hive.state.simulation_state.simulation_state import SimulationState
    from hive.dispatcher.instruction.instruction_interface import Instruction
    from hive.model.vehicle.vehicle import Vehicle
    from hive.util.typealiases import Report, SimTime

from hive.dispatcher.managers.manager_interface import ManagerInterface
from hive.dispatcher.instruction.instructions import DispatchTripInstruction
from hive.state.vehicle_state import Idle, Repositioning
from hive.util.helpers import H3Ops


class GreedyMatcher(NamedTuple, ManagerInterface):
    """
    A managers algorithm that assigns vehicles greedily to most expensive request.
    """
    low_soc_threshold: Ratio

    @staticmethod
    def _gen_report(instruction: Instruction, sim_time: SimTime) -> Report:
        i_dict = instruction._asdict()
        i_dict['sim_time'] = sim_time
        i_dict['report_type'] = "dispatcher"
        i_dict['instruction_type'] = instruction.__class__.__name__

        return i_dict

    def generate_instructions(
            self,
            simulation_state: SimulationState,
    ) -> Tuple[GreedyMatcher, Tuple[Instruction, ...], Tuple[Report, ...]]:
        """
        Generate fleet targets for the dispatcher to execute based on the simulation state.

        :param simulation_state: The current simulation state

        :return: the updated Manager along with fleet targets and reports
        """
        # find requests that need a vehicle. Sorted by price high to low.
        # these instructions override fleet target instructions
        already_dispatched = []
        instructions = ()
        reports = ()

        def _is_valid_for_dispatch(vehicle: Vehicle) -> bool:
            is_valid_state = isinstance(vehicle.vehicle_state, Idle) or \
                             isinstance(vehicle.vehicle_state, Repositioning)

            return bool(vehicle.energy_source.soc > self.low_soc_threshold
                        and is_valid_state and vehicle.id not in already_dispatched)

        unassigned_requests = sorted(
            [r for r in simulation_state.requests.values() if not r.dispatched_vehicle],
            key=lambda r: r.value,
            reverse=True,
        )
        for request in unassigned_requests:
            nearest_vehicle = H3Ops.nearest_entity(geoid=request.origin,
                                                   entities=simulation_state.vehicles,
                                                   entity_search=simulation_state.v_search,
                                                   sim_h3_search_resolution=simulation_state.sim_h3_search_resolution,
                                                   is_valid=_is_valid_for_dispatch)
            if nearest_vehicle:
                instruction = DispatchTripInstruction(
                    vehicle_id=nearest_vehicle.id,
                    request_id=request.id,
                )

                already_dispatched.append(nearest_vehicle.id)

                report = self._gen_report(instruction, simulation_state.sim_time)
                reports = reports + (report,)

                instructions = instructions + (instruction,)

        return self, instructions, reports
