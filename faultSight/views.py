from faultSight import app
from faultSight.database import db, relevant_tables, sites, trials, injections, detections
from faultSight.graphs import get_graph, get_my_graphs
from faultSight.constants import *
from faultSight.utils import *

from flask import render_template, json, jsonify, request

import os, sys
import logging
import numpy as np



# ROUTING CONFIGURATIONS

"""Request for `Entire Application` page"""
@app.route('/')
def index():

    # Gets the default graph (Functions injected into) displayed on the home page
    region_data = generate_region_object()
    main_graph = [get_graph(INJECTED_FUNCTIONS,region_data)]

    # TODO: Need error on main page when no database/no injections(?)
    # Get number of trials
    num_trials = get_num_trials()
    
    return render_template('main.html',
                           functionList = app.config['FUNCTIONS'],
                           injectedFunctionList = app.config['INJECTED_FUNCTIONS'],
                           notInjectedFunctionList = app.config['NOT_INJECTED_FUNCTIONS'],
                           databaseDetails = get_database_tables(),
                           mainGraphList = main_graph,
                           numTrials = num_trials)

"""Request for `Compare Functions` page"""
@app.route('/compareFunctions/')
def compareFunctions():
    # Gets the default graph (Functions injected into) displayed on the home page
    region_data = generate_region_object()
    main_graph = [get_graph(INJECTED_FUNCTIONS,region_data)]

    num_trials = get_num_trials()

    confidence_value = float(read_id_from_config("FaultSight", "confidenceValue"))
    
    return render_template('compareFunctions.html',
                           functionList = app.config['FUNCTIONS'],
                           injectedFunctionList = app.config['INJECTED_FUNCTIONS'],
                           notInjectedFunctionList = app.config['NOT_INJECTED_FUNCTIONS'],
                           databaseDetails = get_database_tables(),
                           mainGraphList = main_graph,
                           numTrials = num_trials,
                           confidenceValue = confidence_value)



"""Request for `Specific Function` page"""
@app.route('/function/<function_name>')
def showFunction(function_name):

    # Returns (Where available):
    #   Partial Code (html formatted)
    #   Values (percentage of injections)
    #   Start line
    #   Highlighted lines
    #   Entire Code (html formatted)
    #   Injections that were not mapped to lines (?)
    #   Fraction of injections in function vs application
    # If the function does not exist, return an error
    if not is_valid_function(function_name):
        return render_template('error.html', functionList = app.config['FUNCTIONS'])




    # Sites relevant to the function, that were injected into
    injected_function_sites = []
    for site in db.session.query(sites)\
                              .join(injections, sites.siteId==injections.siteId)\
                              .filter(sites.func == function_name):
        site_dict = {'file': site.file, 'line': site.line}
        injected_function_sites.append(site_dict)

    # All sites relevant to the function
    all_function_sites = []
    for site in db.session.query(sites)\
                              .filter(sites.func == function_name):
        site_dict = {'file': site.file, 'line': site.line}
        all_function_sites.append(site_dict)


    function_has_injections = (len(injected_function_sites) != 0)


    # Get array of `My Graphs`
    my_graph_list = get_my_graphs(function_name)


    # List of possible file paths - Depending on the database, these may include filepaths that are invalid, so we need to check them
    # For example, some file paths used to be stored as '__NF', if the file was not found during database generation.
    possible_file_paths = [site['file'] for site in all_function_sites]

    possible_file_paths = list(set(possible_file_paths))

    # Parse the list of possible paths, get the correct one
    file_path = get_function_file(possible_file_paths)

    # Get data for statistical analysis
    confidence_value = float(read_id_from_config("FaultSight", "confidenceValue"))
    proportion_testing_results = proportion_test(function_name, confidence_value)

    # Get number of trials
    num_trials = get_num_trials()

    # If we were unable to find a valid file
    if file_path == "":
        # No file found. Perhaps the analysis was run on a different computer and the files have not been transferred over?
        return render_template('missingFunction.html', 
                               functionName=function_name, 
                               functionList = app.config['FUNCTIONS'],  
                               databaseDetails=get_database_tables(),
                               injectedFunctionList = app.config['INJECTED_FUNCTIONS'], 
                               notInjectedFunctionList = app.config['NOT_INJECTED_FUNCTIONS'], 
                               myGraphList=json.dumps(my_graph_list),
                               myGraphListLength=len(my_graph_list),
                               proportionTesting=proportion_testing_results,
                               confidenceValue=float(read_id_from_config("FaultSight", "confidenceValue")),
                               numTrials = num_trials,
                               possibleFilePaths = possible_file_paths)
 

    logging.info("\nRelating injections to source code in file: " +  str(file_path))


    # Get the entire function code - html escaped
    entire_function_html = get_entire_function(file_path)




    # If we have no injections, we cannot proceed further - return what we have so far
    # Why does this page not let you generate graphs?
    if not function_has_injections:
        return render_template('emptyFunction.html', 
                               functionName=function_name, 
                               functionList = app.config['FUNCTIONS'], 
                               entireCode = entire_function_html,  
                               databaseDetails=get_database_tables(),
                               injectedFunctionList = app.config['INJECTED_FUNCTIONS'], 
                               notInjectedFunctionList = app.config['NOT_INJECTED_FUNCTIONS'], 
                               myGraphList=json.dumps(my_graph_list),
                               myGraphListLength=len(my_graph_list),
                               fileName=file_path,
                               numTrials = num_trials)


    # Assumptions we can make now for all functions that reach this point:
    #   - The file which contains this function is valid/exists in the filesystem
    #   - The function has injections



    injected_lines = [site['line'] for site in injected_function_sites] 
    start_line, end_line, line_injection_count, failed_injection = analyse_line_count(injected_lines)

    # Get a list of lines (indexed from 0) that need to be highlighted
    highlight_indexes = get_highlighted_indexes(line_injection_count)

    # Get the partial function code - this is html escaped and ready for highlighting client side.
    partial_function_html = get_subsection_function(file_path, start_line, end_line, highlight_indexes)


    num_injections_in_function = db.session.query(sites)\
                    .join(injections, sites.siteId==injections.siteId)\
                    .filter(sites.func == function_name)\
                    .count()

    # Franction of injections in the function compared to in the application
    fraction_of_injections = float(num_injections_in_function) / app.config['NUM_INJECTIONS']


    

    highlight_lines = highlight_indexes + start_line
    machine_instructions = get_machine_instructions(function_name,highlight_lines, app.config['NUM_INJECTIONS'], num_injections_in_function)
    
    return render_template('function.html', 
                           functionName=function_name, 
                           functionList = app.config['FUNCTIONS'], 
                           injectedFunctionList = app.config['INJECTED_FUNCTIONS'], 
                           notInjectedFunctionList = app.config['NOT_INJECTED_FUNCTIONS'], 
                           failedInjectionPercentage=failed_injection,
                           partialCode=partial_function_html, 
                           partialCodeValues=line_injection_count, 
                           partialHighlightIndexes=highlight_indexes,  
                           machineInstructions=machine_instructions, 
                           highlightMinimumValue=float(read_id_from_config("FaultSight", "highlightValue")),  
                           confidenceValue=float(read_id_from_config("FaultSight", "confidenceValue")),  
                           partialStartLine=start_line, 
                           entireCode=entire_function_html, 
                           myGraphList=json.dumps(my_graph_list), 
                           myGraphListLength=len(my_graph_list), 
                           fractionOfApplciation=fraction_of_injections,  
                           databaseDetails=get_database_tables(),
                           numInjectionsInFunction=num_injections_in_function,
                           fileName=file_path,
                           proportionTesting=proportion_testing_results,
                           statisticalUseAllTrials=read_id_from_config("FaultSight", "statisticalUseAllTrials"),
                           statisticalStartTrial=read_id_from_config("FaultSight", "statisticalStartTrial"),
                           statisticalEndTrial=read_id_from_config("FaultSight", "statisticalEndTrial"),
                           useDynamic=read_id_from_config("FaultSight", "useDynamic"),
                           numTrials = num_trials)



def generate_function_information(function_name):
    function_trials = db.session.query(sites)\
                      .join(injections, sites.siteId==injections.siteId)\
                      .join(trials, injections.trial==trials.trial)\
                      .filter(sites.func == function_name)\
                      .values(trials.trial)

    function_trial_list = [item.trial for item in function_trials]

    num_injections = db.session.query(sites)\
                    .join(injections, sites.siteId==injections.siteId)\
                    .filter(sites.func == function_name)\
                    .count()

    num_detections = db.session.query(detections)\
                    .filter(detections.trial.in_(function_trials))\
                    .count()
           
    num_crashes = db.session.query(trials)\
                    .filter(trials.trial.in_(function_trials))\
                    .filter(trials.crashed == 1)\
                    .count()

    returnDict = {
        'trial_list': function_trial_list,
        'injection_count': num_injections,
        'detection_count': num_detections,
        'crash_count': num_crashes
    }

    return returnDict


def one_tailed_proportion_test_detections(function_a_name, function_b_name, confidence_value):

    function_a_information = generate_function_information(function_a_name)
    function_b_information = generate_function_information(function_b_name)


    # Test of proportions
    p_val_type, p1_val, p2_val, z_value = inequality_test_of_proportions(\
                                            function_a_information['detection_count'], \
                                            function_a_information['injection_count'], \
                                            function_b_information['detection_count'], \
                                            function_b_information['injection_count'])

    return_data = {
        'type': "Detections",
        'p_value': p_val_type,
        'z_value': z_value,
        'p1': {
          'numerator': {
            'title': "Number of detections in function a",
            'value': function_a_information['detection_count']
          },
          'denominator': {
            'title': "Number of injections in function a",
            'value': function_a_information['injection_count']
          },
          'value': p1_val
        },
        'p2': {
          'numerator': {
            'title': "Number of detections in function b",
            'value': function_b_information['detection_count']
          },
          'denominator': {
            'title': "Number of injections in function b",
            'value': function_b_information['injection_count']
          },
          'value': p2_val
        },
        'success': str(p_val_type < (1 - (confidence_value / 100.0 )))
    }




    return return_data


def one_tailed_proportion_test_crashes(function_a_name, function_b_name, confidence_value):

    function_a_information = generate_function_information(function_a_name)
    function_b_information = generate_function_information(function_b_name)



    # Test of proportions
    p_val_type, p1_val, p2_val, z_value = inequality_test_of_proportions(\
                                            function_a_information['crash_count'], \
                                            function_a_information['injection_count'], \
                                            function_b_information['crash_count'], \
                                            function_b_information['injection_count'])


    return_data = {
        'type': "Crashes",
        'p_value': p_val_type,
        'z_value': z_value,
        'p1': {
          'numerator': {
            'title': "Number of crashes in function a",
            'value': function_a_information['crash_count']
          },
          'denominator': {
            'title': "Number of injections in function a",
            'value': function_a_information['injection_count']
          },
          'value': p1_val
        },
        'p2': {
          'numerator': {
            'title': "Number of crashes in function b",
            'value': function_b_information['crash_count']
          },
          'denominator': {
            'title': "Number of injections in function b",
            'value': function_b_information['injection_count']
          },
          'value': p2_val
        },
        'success': str(p_val_type < (1 - (confidence_value / 100.0 )))
    }


    return return_data


def proportion_test(function_name, confidence_value):

    # Array for storing results
    return_data = []

    # Check if user is interested in subset of trials
    use_all_trials = False
    if read_id_from_config("FaultSight", "statisticalUseAllTrials") == "True":
      use_all_trials = True

    min_trial = int(read_id_from_config("FaultSight", "statisticalStartTrial"))
    max_trial = int(read_id_from_config("FaultSight", "statisticalEndTrial"))


    # Type-independent data query
    num_total_sites = calculate_num_sites_for_function(function_name)


    num_total_injections = 0

    if use_all_trials:

        num_total_injections = db.session.query(sites)\
                    .join(injections, sites.siteId==injections.siteId)\
                    .filter(sites.func == function_name)\
                    .count()
    else:

        num_total_injections = db.session.query(sites)\
                    .join(injections, sites.siteId==injections.siteId)\
                    .filter(sites.func == function_name)\
                    .filter(injections.trial >= min_trial)\
                    .filter(injections.trial <= max_trial)\
                    .count()


    
    # Type-dependent queries and calculations
    for type_name in TYPES_WITHOUT_UNKNOWN:

        num_type_injections = 0
        num_type_sites = calculate_num_sites_for_function(function_name, type_name)

        if use_all_trials:

          num_type_injections = db.session.query(sites)\
                                .join(injections, sites.siteId==injections.siteId)\
                                .filter(sites.func == function_name)\
                                .filter(sites.type == type_name)\
                                .count()

        else:
            
          num_type_injections = db.session.query(sites)\
                                .join(injections, sites.siteId==injections.siteId)\
                                .filter(sites.func == function_name)\
                                .filter(sites.type == type_name)\
                                .filter(injections.trial >= min_trial)\
                                .filter(injections.trial <= max_trial)\
                                .count()


        # Test of proportions
        p_val_type, p1_val, p2_val, z_value = test_of_proportions(num_total_injections, num_total_sites, num_type_injections, num_type_sites)

        type_entry = {
            'type': type_name,
            'p_value': p_val_type,
            'z_value': z_value,
            'numTypeInjections': num_type_injections,
            'numTypeSites': num_type_sites,
            'numTotalInjections': num_total_injections,
            'numTotalSites': num_total_sites,
            'p1': p1_val,
            'p2': p2_val,
            'success': str(p_val_type < (1 - (confidence_value / 100.0 ))),
        }


        return_data.append(type_entry)

    return return_data
    
def get_entire_function(file_path):
    # Read the entire function.
    entire_function = read_lines_from_file(file_path)
    entire_function_html = ""
    for i in range(len(entire_function)):
        entire_function_html += str2html(entire_function[i])

    return entire_function_html

# Get a list of indexes that will be highlighted when we show code on page.
def get_highlighted_indexes(values):
    highlight_min_val = int(read_id_from_config("FaultSight", "highlightValue"))
    highlight_indexes = []
    for i in range(len(values)):
        if values[i] > highlight_min_val:
            highlight_indexes.append(i)
    return highlight_indexes

def get_subsection_function(file_path, start_line, end_line, highlight_indexes):
    # Getting 'relevant' lines of code
    relevant_lines_function = read_lines_from_file(file_path, start_line, end_line)
    partial_function = ""

    # Go through each of the relevent lines, and convert string to html
    for i in range(len(relevant_lines_function)):
        if i in highlight_indexes:

            # Convert line to html escaped
            html_line = str2html(relevant_lines_function[i])

            # Add custom link to line
            partial_function += add_custom_link_to_line(html_line)

        # Otherwise just convert to html escaped
        else:
            partial_function += str2html(relevant_lines_function[i])

    return partial_function

def get_function_file(possible_files):
    file = ""
    for possible_file in possible_files:
        if ".LLVM.txt" not in possible_file and "__NF" not in possible_file:
            file = possible_file
            pass

    # Check the file exists, adjust paths if necessary

    # sys.path.insert(0, '../')

    src_path = read_id_from_config("FaultSight", "srcPath")

    # Get filename
    import os.path
    file_name = os.path.basename(file)

    # Get package name - i.e. if srcPath in config file is "/foo/bar/", returns "bar"
    package_name = os.path.basename(src_path)

    # Replace everything before the package name with the srcPath in config file
    new_path = ""
    try:
        dir_name = os.path.dirname(src_path) + "/"
        new_path = file.replace(file[:file.index(package_name)],dir_name )
    except:
        pass

    # Check if the path in the database is correct
    if os.path.isfile(file):
        return file
    elif os.path.isfile(new_path):
        return new_path
    elif os.path.isfile(src_path+file_name):
        return src_path + file
    else:
        logging.warning("Warning: source file not found -- " +  str(file) + " -- nor " + new_path)
        return ""

def analyse_line_count(lines):
    # Finding min and max lines, so we can later select 'relevant' lines.
    minimum = np.min(lines)
    minimum = minimum if minimum >= 0 else 0
    maximum = np.max(lines)+1    
    bins = np.arange(minimum, maximum+1)
    values, bins = np.histogram(lines, bins, density=False) # <------------ check here
    bins = np.arange(minimum, maximum)
    values = 1.*values/np.sum(values)*100 # percents

    # Finds the number of injections that were not mapped to lines.
    failed_injection = 0

    if minimum == 0:
        failed_injection = str(values[0])
        mask = np.all(np.equal(lines, 0), axis=1)
        minimum = np.min(lines[~mask]) - 1
        values = values[minimum:]

    return minimum, maximum, values, failed_injection

    

"""Gets data about the specified function
Parameter - RelevantIndexes contains the index of the highlighted lines, relative to startLine"""
def get_machine_instructions(func, highlight_lines, num_injections_in_application, num_injections_in_function):
    machine_instruction_numbers = []
    # Go through each of the indexes
    for line in highlight_lines:

        num_injections_in_line = db.session.query(sites)\
                                      .join(injections, sites.siteId==injections.siteId)\
                                      .filter(sites.func == func)\
                                      .filter(sites.line == line)\
                                      .count()


        sites_in_line = []


        for site in db.session.query(sites)\
                                      .filter(sites.func == func)\
                                      .filter(sites.line == line):

            num_injections_at_site = db.session.query(sites)\
                                               .join(injections, sites.siteId == injections.siteId)\
                                               .filter(sites.site == site.site)\
                                               .count()

            site_dict = {
                          'Opcode': opcode2Str(site.opcode), 
                          'Comment': site.comment,
                          'Type': site.type,
                          'InjectionCount': num_injections_at_site,
                          'InjectionPercentageLine': num_injections_at_site / float(num_injections_in_line),
                          'InjectionPercentageFunction': num_injections_at_site / float(num_injections_in_function),
                          'InjectionPercentageApplication': num_injections_at_site / float(num_injections_in_application),
                          #'Site': site.site,
                        }

            sites_in_line.append(site_dict)
        machine_instruction_numbers.append(sites_in_line)
    return machine_instruction_numbers


@app.route('/updateFileLocationInDatabase', methods=['POST'])
def update_file_location_in_database():
    file_location = request.json['fileLocation']
    function_name = request.json['functionName']

    db.session.query(sites)\
        .filter(sites.func == function_name)\
        .update({"file": file_location})
    db.session.commit()

    return 'OK'


"""Comparison of functions"""
@app.route('/generateFunctionComparison', methods=['POST'])
def generate_function_comparison():
    function_a =  request.json['functionA']
    function_b =  request.json['functionB']


    comparison_data = generate_function_comparison_data(function_a, function_b)

    return json.dumps(comparison_data)

def generate_function_comparison_data(function_a, function_b):

    confidence_value = float(read_id_from_config("FaultSight", "confidenceValue"))


    # Proportion testing info for function a
    proportion_testing_results_a = proportion_test(function_a, confidence_value)

    # Proportion info for function b
    proportion_testing_results_b = proportion_test(function_b, confidence_value)


    detection_results = one_tailed_proportion_test_detections(function_a, function_b, confidence_value)
    crash_results = one_tailed_proportion_test_crashes(function_a, function_b, confidence_value)

    function_comparison_results = [detection_results, crash_results]

    # General function info for both functions

    general_info_a = generate_function_information(function_a)
    general_info_b = generate_function_information(function_b)

    general_function_results = [general_info_a, general_info_b]

    trial_usage_information = get_trial_usage_information()

    return [proportion_testing_results_a, \
            proportion_testing_results_b, \
            function_comparison_results, \
            general_function_results, \
            trial_usage_information]

def get_trial_usage_information():

    # ConfigParser
    config = generate_config_parser()

    returnDict = {
        'statisticalUseAllTrials':config.get("FaultSight", "statisticalUseAllTrials"),
        'statisticalStartTrial':config.get("FaultSight", "statisticalStartTrial"),
        'statisticalEndTrial':config.get("FaultSight", "statisticalEndTrial")
    }

    return returnDict

# Visualizations section of page - creating a graph

"""Creates a custom graph"""
@app.route('/createGraph', methods=['POST'])
def create_graph():
    focus =  request.json['focus']
    detail = request.json['detail']
    graph_type = request.json['type']

    region_data = generate_region_object(region = request.json['region'], 
                                         start = request.json['regionStart'], 
                                         end = request.json['regionEnd'])

    constraint_data = request.json['constraintArray']


    result_graph = get_graph(detail, region_data, constraint_data)
    return json.dumps(result_graph)


# Settings control

"""Read in config file settings"""
@app.route('/getSettingsFromFile', methods=['GET'])    
def get_settings_from_file():

    # ConfigParser
    config = generate_config_parser()

    # Fill dict with values from config file
    settings_dict = {
        'myGraphList': config.get("FaultSight", "myGraphList"), 
        'customConstraints':config._sections['CustomConstraint'],
        'highlightValue':config.get("FaultSight", "highlightValue"),
        'confidenceValue':config.get("FaultSight", "confidenceValue"),
        'statisticalUseAllTrials':config.get("FaultSight", "statisticalUseAllTrials"),
        'statisticalStartTrial':config.get("FaultSight", "statisticalStartTrial"),
        'statisticalEndTrial':config.get("FaultSight", "statisticalEndTrial"),
        'useDynamic':config.get("FaultSight", "useDynamic")
    }


    if settings_dict['statisticalUseAllTrials'] == "True":
      settings_dict['statisticalUseAllTrials'] = True
    else:
      settings_dict['statisticalUseAllTrials'] = False

    if settings_dict['useDynamic'] == "True":
      settings_dict['useDynamic'] = True
    else:
      settings_dict['useDynamic'] = False
    
    # Package the dict and return
    return jsonify(**settings_dict)
   
"""Save config file changes""" 
@app.route('/saveSettingsToFile', methods=['POST'])
def save_settings_to_file():

    # ConfigParser
    config = generate_config_parser()

    # These are simple to set.
    config.set("FaultSight", "myGraphList", request.json['myGraphList'])
    config.set("FaultSight","highlightValue",request.json['highlightValue'])
    config.set("FaultSight","confidenceValue",request.json['confidenceValue'])

    config.set("FaultSight","statisticalUseAllTrials",request.json['statisticalUseAllTrials'])
    if not request.json['statisticalUseAllTrials']:
      config.set("FaultSight","statisticalStartTrial",request.json['statisticalStartTrial'])
      config.set("FaultSight","statisticalEndTrial",request.json['statisticalEndTrial'])
    else:
      config.set("FaultSight","statisticalStartTrial","0")
      config.set("FaultSight","statisticalEndTrial","0")

    config.set("FaultSight","useDynamic",request.json['useDynamic'])

    # Sets custom constraints - Slightly more complicated
    for key, value in request.json['customConstraints'].items():
        new_list = []
        for item in value:
            item_with_quotes = str("\"") + str(item) + "\""
            new_list.append(item_with_quotes)
        constraint_key = key.encode("utf-8")
        constraint_value = "[" + ",".join(new_list).encode("utf-8") + "]" if isinstance(new_list, list) else new_list.encode("utf-8")
        config.set("CustomConstraint", constraint_key, constraint_value)
    
    # Write to config file
    with open(app.config['CONFIG_PATH'], "wb") as config_file:
        config.write(config_file)

    # We are required to return something.
    return 'OK'
