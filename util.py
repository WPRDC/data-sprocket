import ckanapi
from collections import OrderedDict
from datetime import datetime, timedelta
from icecream import ic

def query_resource(site,query,API_key=None):
    # Use the datastore_search_sql API endpoint to query a CKAN resource.

    # Note that this doesn't work for private datasets.
    # The relevant CKAN GitHub issue has been closed.
    # https://github.com/ckan/ckan/issues/1954

    # In fact, if the dataset is private (the table is inaccessible),
    # the datastore_search_sql function throws a gibberishy, non-helpful error:
    # TypeError: __str__ returned non-string (type dict)

    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    response = ckan.action.datastore_search_sql(sql=query)
    # A typical response is a dictionary like this
    #{u'fields': [{u'id': u'_id', u'type': u'int4'},
    #             {u'id': u'_full_text', u'type': u'tsvector'},
    #             {u'id': u'pin', u'type': u'text'},
    #             {u'id': u'number', u'type': u'int4'},
    #             {u'id': u'total_amount', u'type': u'float8'}],
    # u'records': [{u'_full_text': u"'0001b00010000000':1 '11':2 '13585.47':3",
    #               u'_id': 1,
    #               u'number': 11,
    #               u'pin': u'0001B00010000000',
    #               u'total_amount': 13585.47},
    #              {u'_full_text': u"'0001c00058000000':3 '2':2 '7827.64':1",
    #               u'_id': 2,
    #               u'number': 2,
    #               u'pin': u'0001C00058000000',
    #               u'total_amount': 7827.64},
    #              {u'_full_text': u"'0001c01661006700':3 '1':1 '3233.59':2",
    #               u'_id': 3,
    #               u'number': 1,
    #               u'pin': u'0001C01661006700',
    #               u'total_amount': 3233.59}]
    # u'sql': u'SELECT * FROM "d1e80180-5b2e-4dab-8ec3-be621628649e" LIMIT 3'}
    data = response['records']
    return data

def get_number_of_rows(site,resource_id,API_key=None):
    """Returns the number of rows in a datastore. Note that even when there is a limit
    placed on the number of results a CKAN API call can return, this function will
    still give the true number of rows."""
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    results_dict = ckan.action.datastore_info(id = resource_id)
    ic(results_dict)
    return results_dict['meta']['count']

def get_datastore_dimensions(site, resource_id, include_tooltip=False, API_key=None):
    """Returns dimensions of the datastore, the schema, and an HTML description that
    optionally includes a tooltip giving a list of all field names.

    [ ] The one downside to doing this through the datastore_info endpoint is that
    the returned schema does not maintain the order of the list of fields. To get
    an ordered list of fields it would be necessary to either get the integrated
    data dictionary or get them through another datastore API endpoint like
    datastore_search or datastore_search_sql, but that would require another
    API call. Maybe a nicer way to do this that would be to return the datastore
    description first (since that's what the user ses) and then trigger an AJAX
    call to update the tooltip text in the background."""
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    results_dict = ckan.action.datastore_info(id = resource_id)
    rows = results_dict['meta']['count']
    columns = len(results_dict['schema'])
    schema = results_dict['schema']
    if not include_tooltip:
        datastore_dimensions_description = "{} rows &times; {} columns".format(rows, columns)
    else:
        list_of_fields = ', '.join(schema.keys())
        datastore_dimensions_description = '{} rows &times; <span class="tooltip"><span style="text-decoration-line: underline; text-decoration-style: dotted;">{} columns</span><span class="tooltiptext">{}</span></span>'.format(rows, columns, list_of_fields)
    return datastore_dimensions_description, rows, columns, schema

def get_records_time_series(time_field, unit, span, site, resource_id, API_key=None):
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    assert unit == 'day'
    start_date = (datetime.now() - timedelta(days=1) - timedelta(days=span)).date()
    start_string = start_date.isoformat()
    query = 'SELECT COUNT(*) AS count, DATE("{}") as date FROM "{}" WHERE "{}" >= \'{}\' GROUP BY date ORDER BY date ASC'.format(time_field,resource_id,time_field,start_string)
    data = query_resource(site,query,API_key)
    counts = [period['count'] for period in data]
    counts_by_date = OrderedDict()
    for offset in range(0,30):
        sample_date = start_date + timedelta(days=offset)
        counts_by_date[str(sample_date)] = 0
    for row in data:
        counts_by_date[row['date']] = row['count']
    ic(counts_by_date)
    return list(counts_by_date.values())
