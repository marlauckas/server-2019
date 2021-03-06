#!/usr/bin/python3.6
"""Calculates points prevented by a defender in all TIMDs and Teams.

TIMD stands for Team in Match Data"""
# External imports
import json
import os
import subprocess
# Internal imports
import utils

# Extracts TIMDs from cache and organizes them by match.
TIMDS_BY_MATCH = {}
for timd in os.listdir(utils.create_file_path('data/cache/timds')):
    with open(utils.create_file_path(f'data/cache/timds/{timd}'), 'r') as file:
        timd_data = json.load(file)
    if timd_data.get('calculatedData') is not None:
        # .split() removes '.json' file ending
        timd_name = timd.split('.')[0]
        match_number = timd_name.split('Q')[1]
        # Creates a blank dictionary for a match if it doesn't exist yet.
        if TIMDS_BY_MATCH.get(match_number) is None:
            TIMDS_BY_MATCH[match_number] = {}
        TIMDS_BY_MATCH[match_number][timd_name] = timd_data

# Teams that have played defense in 1 or more matches
DEFENDER_TEAMS = set()

for match_number, timds in TIMDS_BY_MATCH.items():
    # Pulls match schedule (for a single match from cache
    with open(utils.create_file_path(
            f'data/cache/match_schedule/{match_number}.json'), 'r') as file:
        match_schedule = json.load(file)

    timds_by_alliance = {
        'red': {},
        'blue': {},
    }
    # A defending TIMD is a TIMD in which the scouted robot played
    # defense on another robot.
    defending_timds_by_alliance = {
        'red': {},
        'blue': {},
    }
    red_alliance = match_schedule['redTeams']
    blue_alliance = match_schedule['blueTeams']
    for timd_name, timd_data in timds.items():
        # Extracts 'team_number' from 'timd_name'.
        # 'team_number' is a string.
        team_number = timd_name.split('Q')[0]
        if team_number in red_alliance:
            alliance = 'red'
        elif team_number in blue_alliance:
            alliance = 'blue'
        else:
            print('Error: TIMD is not in match schedule.')

        timds_by_alliance[alliance][timd_name] = timd_data

        # Checks if defense was played
        if timd_data['calculatedData'].get('timeDefending', 0) > 0:
            defending_timds_by_alliance[alliance][timd_name] = timd_data

    for alliance, timds_ in defending_timds_by_alliance.items():
        # TIMD to its timeline
        timelines = {timd_name: timd_data['timeline'] for timd_name,
                     timd_data in timds_.items()}

        for timd, timeline in timelines.items():
            time_pairs = []
            # Used to prevent two of the same actions back-to-back
            # (e.g. two 'startDefense' actions in a row)
            last_action_type = None
            # Time of last 'startDefense' action
            last_start_defense = None
            for action in timeline:
                if action['type'] in ['startDefense', 'endDefense']:
                    # Prevents two of the same actions back-to-back
                    if action['type'] != last_action_type:
                        last_action_type = action['type']
                        time = action['time']
                        if action['type'] == 'startDefense':
                            last_start_defense = time
                        elif action['type'] == 'endDefense':
                            time_pairs.append((last_start_defense, time))
                        else:
                            print(f"Error: Unexpected type '{action['type']}'")
            # 'endDefense' is automatically added at 0.0 by the Scout
            # app, so we do not need to add handling for timelines that
            # the end with 'startDefense'.

            # If only 1 team defends, we can attribute all defended
            # cycles to that team.
            if len(timelines) == 1:
                time_pairs = [(135.0, 0.0)]

            # Extracts 'team_number' from 'timd'.
            # 'team_number' is a string.
            team_number = timd.split('Q')[0]
            if team_number in red_alliance:
                opposite_alliance_timds = timds_by_alliance['blue']
            else:
                opposite_alliance_timds = timds_by_alliance['red']

            # Each opposing team that the team defended to the cycles the
            # opposing team was defended in
            defended_cycles_by_team = {}
            for timd_name, timd_data in opposite_alliance_timds.items():
                # Extracts 'team_number' from 'timd_name'.
                # 'team_number' is a string.
                team_number = timd_name.split('Q')[0]
                defended_cycles = []
                intake_time = None
                if timd_data.get('timeline') is None:
                    continue
                # Removes the first item in the timeline if it is a
                # placement or drop because it is not a full cycle.
                if timd_data['timeline'][0]['type'] in ['placement', 'drop']:
                    timd_data['timeline'] = timd_data['timeline'][1:]
                for action in timd_data['timeline']:
                    if action.get('wasDefended', False) is False:
                        if action['type'] == 'intake':
                            intake_time = action['time']
                            game_piece = action['piece']
                        continue
                    time = action['time']
                    for start_time, end_time in time_pairs:
                        # Time counts down from 150.0 to 0.0
                        # Checks if 'time' is between 'start_time' and
                        # 'end_time'
                        if start_time > time > end_time:
                            action['intakeTime'] = intake_time
                            action['piece'] = game_piece
                            defended_cycles.append(action)
                if defended_cycles != []:
                    defended_cycles_by_team[team_number] = defended_cycles

            alliance_points_prevented = {}
            alliance_failed_cycles_caused = {}
            for team, defended_cycles in defended_cycles_by_team.items():
                # Counters of how many drops, fails, and cycles there
                # are for each game element.
                drops = {'cargo': 0, 'panel': 0}
                fails = {'cargo': 0, 'panel': 0}
                cycles = {'cargo': 0, 'panel': 0}
                cycle_times = {'cargo': [], 'panel': []}
                for action in defended_cycles:
                    piece = action['piece']
                    cycles[piece] += 1
                    if action['type'] == 'placement':
                        if action['didSucceed'] is False:
                            fails[piece] += 1
                        else:
                            time = action['time']
                            cycle_times[piece].append(
                                action['intakeTime'] - time)
                    elif action['type'] == 'drop':
                        drops[piece] += 1
                # Calculates the drop and fail rate of the team under defense
                defended_drop_rate = {
                    'cargo': None if cycles['cargo'] == 0 else \
                        drops['cargo']/cycles['cargo'],
                    'panel': None if cycles['panel'] == 0 else \
                        drops['panel']/cycles['panel']
                }
                defended_fail_rate = {
                    'cargo': None if cycles['cargo'] == 0 else \
                        fails['cargo']/cycles['cargo'],
                    'panel': None if cycles['panel'] == 0 else \
                        fails['panel']/cycles['panel']
                }
                # Pulls calculated data
                with open(utils.create_file_path(
                        f'data/cache/teams/{team}.json'), 'r') as file:
                    calculated_data = json.load(file)['calculatedData']
                # Points prevented on a single team
                points_prevented = {}
                failed_cycles_caused = {}
                for piece in ['cargo', 'panel']:
                    if cycles[piece] == 0:
                        continue
                    # Uses a team's calculated data to find their
                    # average drop and fail rate to compare with the
                    # defended drop/fail rate.
                    avg_drops = calculated_data[f'avg{piece.capitalize()}Drops']
                    avg_fails = calculated_data[f'avg{piece.capitalize()}Fails']
                    avg_cycles = calculated_data[f'avg{piece.capitalize()}Cycles']
                    avg_drop_rate = avg_drops/avg_cycles
                    avg_fail_rate = avg_fails/avg_cycles
                    avg_cycle_time = calculated_data[f'{piece}CycleAll']
                    lost_time = sum([cycle_time - avg_cycle_time for
                                     cycle_time in cycle_times[piece]])
                    drops_caused = (defended_drop_rate[piece]-avg_drop_rate)*drops[piece]
                    fails_caused = (defended_fail_rate[piece]-avg_fail_rate)*fails[piece]

                    # Cycles lost from slowed cycles
                    lost_cycles = lost_time/avg_cycle_time
                    if piece == 'cargo':
                        points = 3
                    else:
                        points = 2
                    points_prevented[piece] = points*(drops_caused+fails_caused+lost_cycles)
                    failed_cycles_caused[piece] = drops_caused + fails_caused
                alliance_points_prevented[team] = points_prevented
                alliance_failed_cycles_caused[team] = failed_cycles_caused

            # Saves TIMD points prevented
            cargo_points_prevented = 0
            panel_points_prevented = 0
            cargo_failed_cycles_caused = 0
            panel_failed_cycles_caused = 0
            for team_data in alliance_points_prevented.values():
                cargo_points_prevented += team_data.get('cargo', 0)
                panel_points_prevented += team_data.get('panel', 0)
            for team_data in alliance_failed_cycles_caused.values():
                cargo_failed_cycles_caused += team_data.get('cargo', 0)
                panel_failed_cycles_caused += team_data.get('panel', 0)
            update_dict = {
                'cargoPointsPrevented': cargo_points_prevented,
                'panelPointsPrevented': panel_points_prevented,
                'pointsPrevented': cargo_points_prevented + \
                    panel_points_prevented,
                'superCargoFailedCyclesCaused': cargo_failed_cycles_caused,
                'superPanelFailedCyclesCaused': panel_failed_cycles_caused,
                'superFailedCyclesCaused': cargo_failed_cycles_caused + \
                    panel_failed_cycles_caused,
            }
            for folder in ['cache', 'upload_queue']:
                try:
                    with open(f'data/{folder}/timds/{timd}.json',
                              'r') as file:
                        file_data = json.load(file)
                except FileNotFoundError:
                    file_data = {}
                if file_data.get('calculatedData') is None:
                    file_data['calculatedData'] = {}
                file_data['calculatedData'].update(update_dict)
                with open(f'data/{folder}/timds/{timd}.json',
                          'w') as file:
                    json.dump(file_data, file)
            DEFENDER_TEAMS.add(team_number)

# Calls 'calculate_team' to calculate team defense data points.
for team in DEFENDER_TEAMS:
    subprocess.call(f'python3 calculate_team.py {team}', shell=True)
