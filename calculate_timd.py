#!/usr/bin/python3.6
"""Calculations for a single TIMD.

TIMD stands for Team In Match Data.  TIMD calculations include
consolidation of (up to) 3 tempTIMDs (temporary TIMDs) into a single
TIMD, and the calculation of data points that are reflective of a team's
performance in a single match.

Consolidation is the process of determining the actions a robot
performed in a match by using data from (up to) 3 tempTIMDs.  One
tempTIMD is created per scout per match.  Ideally, 18 scouts are
distributed evenly across the 6 robots per match, resulting in 3
tempTIMDs per robot per match (aka 3 tempTIMDs per TIMD).  However, the
number of tempTIMDs per TIMD may be less than 3, depending on scout
availability, incorrect scout distribution, or missing data.

Called by server.py with the name of the TIMD to be calculated."""
# External imports
import json
import os
import sys
import subprocess
# Internal imports
import consolidation
import decompressor
import utils

def percent_success(actions):
    """Finds the percent of times didSucceed is true in a list of actions.

    actions is the list of actions that can either succeed or fail."""
    successes = [action.get('didSucceed') for action in actions]
    # Returns the integer percentage of times in successes that
    # didSucceed is true. Taking an average of a list of booleans
    # returns a float between 0 and 1 of what percentage of times the
    # value was True.
    # Example: [True, True, False, True] returns 75.
    return round(100 * utils.avg(successes))

def filter_cycles(cycle_list, **filters):
    """Puts cycles through filters to meet specific requirements.

    cycle_list is a list of tuples where the first item is an intake and
    the second action is a placement or drop.
    filters are the specifications that certain data points inside the
    cycles must fit to be included in the returned cycles.
    example for filter - 'level=1' as an argument, '{'level': 1}' inside
    the function."""
    filtered_cycles = []
    # For each cycle, if any of the specifications are not met, the
    # loop breaks and moves on to the next cycle, but if all the
    # specifications are met, the cycle is added to the filtered cycles.
    for cycle in cycle_list:
        for data_field, requirement in filters.items():
            # Handling for the cargo ship in level 1 placements.
            if data_field == 'level' and requirement == 1:
                # If no level is specified, it is a cargo ship placement.
                if cycle[1].get('level', 1) != 1:
                    break
            # Otherwise, the requirement is checked normally
            else:
                if cycle[1].get(data_field) != requirement:
                    break
        # If all the requirements are met, the cycle is added to the
        # (returned) filtered cycles.
        else:
            filtered_cycles.append(cycle)
    return filtered_cycles

def calculate_avg_cycle_time(cycles):
    """Calculates the average time for an action based on start and end times.

    Finds the time difference between each action pair passed, then
    returns the average of the differences.
    cycles is a list of tuples where the first action in the tuple is
    the intake, and the second item is the placement or drop."""
    cycle_times = []
    for cycle in cycles:
        # Subtracts the second time from the first because the time
        # counts down in the timeline.
        cycle_times.append(cycle[0].get('time') -
                           cycle[1].get('time'))
    return utils.avg(cycle_times, None)

def calculate_total_action_duration(cycles):
    """Calculates the total duration of an action based on start and end times.

    Finds the time difference between each action pair passed and
    returns the sum of the differences.  Used for both defense and incap
    cycles.

    cycles is a list of tuples where the first action marks the start of
    a period (incap or defense), and the second action marks the end of
    that period."""
    cycle_times = []
    for cycle in cycles:
        # Subtracts the second time from the first because the time
        # counts down in the timeline.
        cycle_times.append(cycle[0].get('time') -
                           cycle[1].get('time'))
    return sum(cycle_times)

def filter_timeline_actions(timd, **filters):
    """Puts a timeline through a filter to use for calculations.

    timd is the TIMD that needs calculated data.
    filters are the specifications that certain data points inside the
    timeline must fit in order to be included in the returned timeline.
    example for filter - 'level=1' as an argument, '{'level': 1}' inside
    the function."""
    filtered_timeline = []
    # For each action, if any of the specifications are not met, the
    # loop breaks and moves on to the next action, but if all the
    # specifications are met, the action is added to the filtered
    # timeline.
    for action in timd.get('timeline', []):
        for data_field, requirement in filters.items():
            # Handling for the cargo ship in level 1 placements.
            if data_field == 'level' and requirement == 1:
                # If no level is specified, it is a cargo ship placement.
                if action.get('level', 1) != 1:
                    break
            elif data_field == 'zone' and requirement == 'loadingStation':
                if action['zone'] not in ['leftLoadingStation',
                                          'rightLoadingStation']:
                    break
            # If the filter specifies time, it can either specify
            # sandstorm by making the requirement 'sand' or specify
            # teleop by making the requirement 'tele'.
            #TODO: Rename 'sand' and 'tele'
            elif data_field == 'time':
                if requirement == 'sand' and action['time'] <= 135.0:
                    break
                elif requirement == 'tele' and action['time'] > 135.0:
                    break
            # Otherwise, it checks the requirement normally
            else:
                if action.get(data_field) != requirement:
                    break
        # If all the requirements are met, the action is added to the
        # (returned) filtered timeline.
        else:
            filtered_timeline.append(action)
    return filtered_timeline

def make_paired_cycle_list(cycle_list):
    """Pairs up cycles together into tuples.

    cycle_list is the list of actions that need to be paired up."""
    # [::2] are the even-indexed items of the list, [1::2] are the
    # odd-indexed items of the list. The python zip function puts
    # matching-index items from two lists into tuples.
    return list(zip(cycle_list[::2], cycle_list[1::2]))

def calculate_timd_data(timd):
    """Calculates data in a timd and adds it to 'calculatedData' in the TIMD.

    timd is the TIMD that needs calculated data."""
    calculated_data = {}

    # Adds counting data points to calculated data, does this by setting
    # the key to be the sum of a list of ones, one for each time the
    # given requirements are met. This creates the amount of times those
    # requirements were met in the timeline.
    calculated_data['cargoScored'] = len(filter_timeline_actions(
        timd, type='placement', didSucceed=True, piece='cargo'))
    calculated_data['panelsScored'] = len(filter_timeline_actions(
        timd, type='placement', didSucceed=True, piece='panel'))
    calculated_data['cargoFouls'] = len(filter_timeline_actions(
        timd, shotOutOfField=True))
    calculated_data['pinningFouls'] = len(filter_timeline_actions(
        timd, type='pinningFoul'))

    calculated_data['cargoCycles'] = len(filter_timeline_actions(
        timd, type='intake', piece='cargo'))
    calculated_data['panelCycles'] = len(filter_timeline_actions(
        timd, type='intake', piece='panel'))

    cycle_actions = [action for action in timd.get('timeline', []) if \
        action['type'] in ['placement', 'intake', 'drop']]
    if len(cycle_actions) > 0:
        # If the last action is an intake, it shouldn't count as a
        # cycle, so it is subtracted from its cycle data field.
        if cycle_actions[-1]['type'] == 'intake':
            piece = cycle_actions[-1]['piece']
            # HACK: Subtracts the extra intake from the already
            # calculated number of cycles. Should be included in that
            # calculation.
            calculated_data[f'{piece}Cycles'] -= 1

    calculated_data['cargoDrops'] = len(filter_timeline_actions(
        timd, type='drop', piece='cargo'))
    calculated_data['panelDrops'] = len(filter_timeline_actions(
        timd, type='drop', piece='panel'))
    calculated_data['cargoFails'] = len(filter_timeline_actions(
        timd, type='placement', didSucceed=False, piece='cargo'))
    calculated_data['panelFails'] = len(filter_timeline_actions(
        timd, type='placement', didSucceed=False, piece='panel'))

    calculated_data['cargoScoredSandstorm'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        didSucceed=True, time='sand'))
    calculated_data['panelsScoredSandstorm'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        didSucceed=True, time='sand'))
    calculated_data['cargoScoredTeleL1'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=1, didSucceed=True, time='tele'))
    calculated_data['cargoScoredTeleL2'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=2, didSucceed=True, time='tele'))
    calculated_data['cargoScoredTeleL3'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=3, didSucceed=True, time='tele'))
    calculated_data['panelsScoredTeleL1'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=1, didSucceed=True, time='tele'))
    calculated_data['panelsScoredTeleL2'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=2, didSucceed=True, time='tele'))
    calculated_data['panelsScoredTeleL3'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=3, didSucceed=True, time='tele'))

    calculated_data['cargoScoredL1'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=1, didSucceed=True))
    calculated_data['cargoScoredL2'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=2, didSucceed=True))
    calculated_data['cargoScoredL3'] = len(
        filter_timeline_actions(timd, type='placement', piece='cargo', \
        level=3, didSucceed=True))
    calculated_data['panelsScoredL1'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=1, didSucceed=True))
    calculated_data['panelsScoredL2'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=2, didSucceed=True))
    calculated_data['panelsScoredL3'] = len(
        filter_timeline_actions(timd, type='placement', piece='panel', \
        level=3, didSucceed=True))

    calculated_data['totalFailedCyclesCaused'] = sum([
        action['failedCyclesCaused'] for action in
        filter_timeline_actions(timd, type='endDefense')])

    # The next set of calculated data points are the success
    # percentages, these are the percentages (displayed as an integer)
    # of didSucceed for certain actions, such as the percentage of
    # success a team has loading panels.
    calculated_data['panelLoadSuccess'] = percent_success(
        filter_timeline_actions(timd, type='intake', piece='panel',
                                zone='loadingStation'))
    calculated_data['cargoSuccessAll'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo'))
    calculated_data['cargoSuccessDefended'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo',
                                wasDefended=True))
    calculated_data['cargoSuccessUndefended'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo',
                                wasDefended=False))
    calculated_data['cargoSuccessL1'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo',
                                level=1))
    calculated_data['cargoSuccessL2'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo',
                                level=2))
    calculated_data['cargoSuccessL3'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='cargo',
                                level=3))

    calculated_data['panelSuccessAll'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel'))
    calculated_data['panelSuccessDefended'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel',
                                wasDefended=True))
    calculated_data['panelSuccessUndefended'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel',
                                wasDefended=False))
    calculated_data['panelSuccessL1'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel',
                                level=1))
    calculated_data['panelSuccessL2'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel',
                                level=2))
    calculated_data['panelSuccessL3'] = percent_success(
        filter_timeline_actions(timd, type='placement', piece='panel',
                                level=3))

    # Creates the cycle_list, a list of tuples where the intake is the
    # first item and the placement or drop is the second. This is used
    # when calculating cycle times.
    cycle_list = []
    for action in timd.get('timeline', []):
        if action.get('type') in ['intake', 'placement', 'drop']:
            # If the action is a failed loading station intake, it
            # shouldn't play a part in cycles, so it is filtered out.
            if not (action.get('type') == 'intake' and
                    action.get('didSucceed') is False):
                cycle_list.append(action)

    # There must be at least 2 actions to have a cycle.
    if len(cycle_list) > 1:
        # If the first action in the list is a placement, it is a
        # preload, which doesn't count when calculating cycle times.
        if cycle_list[0].get('type') in ['placement', 'drop']:
            cycle_list.pop(0)
        # If the last action in the list is an intake, it means the
        # robot finished with a game object, in which the cycle was
        # never completed.
        if cycle_list[-1].get('type') == 'intake':
            cycle_list.pop(-1)
        paired_cycle_list = make_paired_cycle_list(cycle_list)

        calculated_data['cargoCycleAll'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='cargo'))
        calculated_data['cargoCycleL1'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='cargo', level=1))
        calculated_data['cargoCycleL2'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='cargo', level=2))
        calculated_data['cargoCycleL3'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='cargo', level=3))

        calculated_data['panelCycleAll'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='panel'))
        calculated_data['panelCycleL1'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='panel', level=1))
        calculated_data['panelCycleL2'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='panel', level=2))
        calculated_data['panelCycleL3'] = calculate_avg_cycle_time(
            filter_cycles(paired_cycle_list, piece='panel', level=3))

    # Calculates if a team is incap throughout the entirety of the match
    # by checking if they have any actions in the match other than incap
    # and unincap. If they don't have any other actions, they were incap
    # the entire match.
    for action in timd.get('timeline', []):
        if action.get('type') not in ['incap', 'unincap'] and \
                action.get('time') <= 135.0:
            calculated_data['isIncapEntireMatch'] = False
            break
    else:
        calculated_data['isIncapEntireMatch'] = True

    # Creates a list of the climb dictionary or nothing if there is no
    # climb. If there is a climb, the time of the climb is the amount
    # of time they spent climbing.
    for action in timd.get('timeline', []):
        if action['type'] == 'climb':
            calculated_data['timeClimbing'] = action['time']
            calculated_data['selfClimbLevel'] = action['actual']['self']
            calculated_data['robot1ClimbLevel'] = action['actual']['robot1']
            calculated_data['robot2ClimbLevel'] = action['actual']['robot2']

    # Creates a list of all the incap and unincap actions in the timeline.
    incap_items = []
    for action in timd.get('timeline', []):
        if action.get('type') in ['incap', 'unincap']:
            incap_items.append(action)
    if len(incap_items) > 0:
        # If the last action in the list is an incap, it means they
        # finished the match incap, so it adds an unincap at the end of
        # the timeline.
        if incap_items[-1]['type'] == 'incap':
            incap_items.append({'type': 'unincap', 'time': 0.0})
        paired_incap_list = make_paired_cycle_list(incap_items)

        # Calculates the timeIncap by calculating the total amount of
        # time the robot spent incap during the match.
        calculated_data['timeIncap'] = calculate_total_action_duration(
            paired_incap_list)
    else:
        # Otherwise, the time that the robot spent incap is naturally 0.
        calculated_data['timeIncap'] = 0.0

    # Creates a list of all the startDefense and endDefense actions in
    # the timeline.
    defense_items = []
    for action in timd.get('timeline', []):
        if action['type'] in ['startDefense', 'endDefense']:
            defense_items.append(action)
    if len(defense_items) > 0:
        paired_defense_list = make_paired_cycle_list(defense_items)
        # 'timeDefending' is the total amount of time the robot spent
        # defending during the match.
        calculated_data['timeDefending'] = calculate_total_action_duration(
            paired_defense_list)
    else:
        # Otherwise, the time that the robot spent defending is naturally 0.
        calculated_data['timeDefending'] = 0.0
    return calculated_data

# Check to ensure TIMD name is being passed as an argument
if len(sys.argv) == 2:
    # Extract TIMD name from system argument
    TIMD_NAME = sys.argv[1]
else:
    print('Error: TIMD name not being passed as an argument. Exiting...')
    sys.exit(0)

COMPRESSED_TIMDS = []

TEMP_TIMDS = {}

# Goes into the temp_timds folder to get the names of all the tempTIMDs
# that correspond to the given TIMD. Afterwards, the tempTIMDs are
# decompressed and addded them to the TEMP_TIMDS dictionary with the
# scout name as the key and the decompressed tempTIMD as the value.
# This is needed for the consolidation function
for temp_timd in os.listdir(utils.create_file_path('data/cache/temp_timds')):
    if temp_timd.split('-')[0] == TIMD_NAME:
        file_path = utils.create_file_path(
            f'data/cache/temp_timds/{temp_timd}')
        with open(file_path, 'r') as file:
            compressed_temp_timd = file.read()
        decompressed_temp_timd = list(decompressor.decompress_temp_timd(
            compressed_temp_timd).values())[0]
        scout_name = decompressed_temp_timd.get('scoutName')
        TEMP_TIMDS[scout_name] = decompressed_temp_timd

# After the TEMP_TIMDS are decompressed, they are fed into the
# consolidation script where they are returned as one final TIMD.
FINAL_TIMD = consolidation.consolidate_temp_timds(TEMP_TIMDS)

# Adds the matchNumber and teamNumber necessary for later team calcs.
FINAL_TIMD['matchNumber'] = int(TIMD_NAME.split('Q')[1])
FINAL_TIMD['teamNumber'] = int(TIMD_NAME.split('Q')[0])

# Adds calculatedData to the FINAL_TIMD using the
# add_calculated_data_to_timd function at the top of the file.
FINAL_TIMD['calculatedData'] = calculate_timd_data(FINAL_TIMD)

# Save data in local cache
with open(utils.create_file_path(f'data/cache/timds/{TIMD_NAME}.json'),
          'w') as file:
    json.dump(FINAL_TIMD, file)

# Save data in Firebase upload queue
with open(utils.create_file_path(
        f'data/upload_queue/timds/{TIMD_NAME}.json'), 'w') as file:
    json.dump(FINAL_TIMD, file)

# TODO: Make 'forward_temp_super' more efficient (call it less often)
subprocess.call(f'python3 forward_temp_super.py', shell=True)

# After the timd is calculated, the team is calculated.
TEAM = TIMD_NAME.split('Q')[0]
subprocess.call(f'python3 calculate_team.py {TEAM}', shell=True)
