import ckanapi
from icecream import ic

def get_number_of_rows(site,resource_id,API_key=None):
    """Returns the number of rows in a datastore. Note that even when there is a limit
    placed on the number of results a CKAN API call can return, this function will
    still give the true number of rows."""
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    results_dict = ckan.action.datastore_info(id = resource_id)
    ic(results_dict)
    return results_dict['meta']['count']

def get_datastore_dimensions(site, resource_id, API_key=None):
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    results_dict = ckan.action.datastore_info(id = resource_id)
    rows = results_dict['meta']['count']
    columns = len(results_dict['schema'])
    datastore_dimensions_description = "{} rows &times; {} columns".format(rows, columns) 
    return datastore_dimensions_description, rows, columns
