from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django import forms
import ckanapi, json
from collections import defaultdict, OrderedDict
from pprint import pprint

from .util import get_datastore_dimensions, get_records_time_series

from icecream import ic
# [ ] All CKAN API requests should be API-key-free to avoid any possibility of tables
# being dropped or data being modified.
#     [ ] Implement other SQL injection attack defenses:
#         * https://www.slideshare.net/openpbs/sql-injection-defense-in-python

# [ ] Implement SQLite output (maybe by using dataset).
#     [ ] Think about putting limits on the output size and deciding between keeping the SQLite
#         database in memory versus storing it in a temporary file (limiting the memory footprint).
#         * Maybe only offer SQLite output for some maximum number of rows ==> Switch to Jinja templates.
#     * Also, if SQLite output is a general CKAN feature we would like, should SQLite conversion
#     be a sepaate function/module/API?

# [ ] Implement a smart limiter which estimates the memory footprints required by running this script
# and processing the query on the CKAN instance and adjusts as necessary.

# Front-end stuff
# [ ] Implement GUI (probably using JQuery Query Builder, though also consider django-report-builder)
# [ ] Add checkbox to drop duplicate rows and implement by changing SELECT to SELECT DISTINCT.

def get_site():
    return "https://data.wprdc.org"

def get_resource_parameter(site,resource_id,parameter=None,API_key=None):
    # Some resource parameters you can fetch with this function are
    # 'cache_last_updated', 'package_id', 'webstore_last_updated',
    # 'datastore_active', 'id', 'size', 'state', 'hash',
    # 'description', 'format', 'last_modified', 'url_type',
    # 'mimetype', 'cache_url', 'name', 'created', 'url',
    # 'webstore_url', 'mimetype_inner', 'position',
    # 'revision_id', 'resource_type'
    # Note that 'size' does not seem to be defined for tabular
    # data on WPRDC.org. (It's not the number of rows in the resource.)
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    metadata = ckan.action.resource_show(id=resource_id)
    if parameter is None:
        return metadata
    else:
        return metadata[parameter]

def get_package_parameter(site,package_id,parameter=None,API_key=None):
    """Gets a CKAN package parameter. If no parameter is specified, all metadata
    for that package is returned."""
    # Some package parameters you can fetch from the WPRDC with
    # this function are:
    # 'geographic_unit', 'owner_org', 'maintainer', 'data_steward_email',
    # 'relationships_as_object', 'access_level_comment',
    # 'frequency_publishing', 'maintainer_email', 'num_tags', 'id',
    # 'metadata_created', 'group', 'metadata_modified', 'author',
    # 'author_email', 'state', 'version', 'department', 'license_id',
    # 'type', 'resources', 'num_resources', 'data_steward_name', 'tags',
    # 'title', 'frequency_data_change', 'private', 'groups',
    # 'creator_user_id', 'relationships_as_subject', 'data_notes',
    # 'name', 'isopen', 'url', 'notes', 'license_title',
    # 'temporal_coverage', 'related_documents', 'license_url',
    # 'organization', 'revision_id'
    ckan = ckanapi.RemoteCKAN(site, apikey=API_key)
    metadata = ckan.action.package_show(id=package_id)
    if parameter is None:
        return metadata
    else:
        if parameter in metadata:
            return metadata[parameter]
        else:
            return None

def extract_tags(metadata):
    return [t['name'] for t in metadata['tags']]

def extend_resource(r,p=None):
    if p is None: # The package metadata wasn't passed, so obtain it.
        site = get_site()
        p_id = get_resource_parameter(site,r['id'],'package_id')
        p = get_package_parameter(site,p_id)

    if 'format' not in r or r['format'] == '':
        r['format'] = 'None'
    elif r['format'] == 'HTML':
        if 'url' in r and 'data.wprdc.org' not in r['url']:
            r['format'] = "HTML (opens external link)"

    r['csv_download_link'] = ''
    if r['url_type'] in ['datapusher']:
        r['csv_download_link'] = r['url']
    elif r['url_type'] in ['upload'] and r['format'] in ['CSV', 'csv']:
        r['csv_download_link'] = r['url']
    elif r['url'][-3:].lower() == 'csv':
        r['csv_download_link'] = r['url']
    else: # 'csv_download_link' has not been assigned
        if 'datastore_active' in r and r['datastore_active']: # but it should be if there is a datastore.
            r['csv_download_link'] = "https://tools.wprdc.org/downstream/{}/csv".format(r['id'])

    r['ckan_resource_page_url'] = get_site() + "/dataset/" + p['name'] + "/resource/" + r['id']
    time_field = None
    if 'extras' in p:
        for extra in p['extras']:
            if extra['key'] == 'time_field':
                time_field_lookup = json.loads(extra['value'])
                if r['id'] in time_field_lookup:
                    time_field = '{}'.format(time_field_lookup[r['id']])
    r['time_field'] = time_field
    return r

def injectable_formatted_html(d):
    s = ""
    for field, value in d.items():
        s += "&nbsp;&nbsp;&nbsp;<b>{}:</b> {}<br>".format(field, value)
    return s

def get_sparklines(request):
    """
    Generate sparklines if the datastore and time_field are defined.
    """
    resource_id = request.GET.get('resource_id', None)
    datastore_exists = request.GET.get('datastore_exists', None)
    time_field = request.GET.get('time_field', None)
    unit = request.GET.get('unit', 'day')
    span = int(request.GET.get('span', 0))

    if resource_id is None or not datastore_exists or time_field in ['', None] or span==0:
        data = { 'counts': [] }
        return JsonResponse(data)

    #### [ ] Write the query below to find the number of records for each of the last 30 days (or whatever).
    site = get_site()
    try:
        counts = get_records_time_series(time_field, unit, span, site, resource_id, API_key=None)
        #counts_by_month = get_records_time_series(time_field, 'month', 12, site, resource_id, API_key=None)
        #ic(counts)
        data = { 'counts': counts }
    except ckanapi.errors.NotFound: # if there's no datastore for this resource ID.
        data = { 'counts': [] }
    return JsonResponse(data)

def get_datastore(request):
    """
    Look up the datastore and return its parameters.
    """
    resource_id = request.GET.get('resource_id', None)
    if resource_id is None:
        data = {}
        return JsonResponse(data)

    site = get_site()
    try:
        datastore_dimensions_description, rows, columns, schema = get_datastore_dimensions(site, resource_id, include_tooltip=True)
        data = {
            'rows': rows,
            'columns': columns,
            'd': datastore_dimensions_description,
            'schema': schema
            #'field_names': datastore_info['schema'] # It might be better just to get and display the integrated data dictionary.
        }
    except ckanapi.errors.NotFound: # if there's no datastore for this resource ID.
        data = {'d': 'None'}
    return JsonResponse(data)

def get_resource(request):
    """
    Look up the resource and return its parameters.
    """
    resource_id = request.GET.get('resource_id', None)
    if resource_id is None:
        data = {}
        return JsonResponse(data)

    ckan = ckanapi.RemoteCKAN(get_site())
    metadata = ckan.action.resource_show(id=resource_id)
    metadata = extend_resource(metadata)

    data = {
        'resource': metadata,
        'resource_metadata': injectable_formatted_html(metadata),

    }
    return JsonResponse(data)

def extend_package(p):
    p['plain_tags'] = ', '.join(extract_tags(p))
    p['dataset_url'] = get_site() + "/dataset/" + p['name']
    p['selected_extras'] = []
    if 'extras' in p:
        extras = p['extras']
        boring_fields = ['dcat_issued', 'dcat_modified', 'dcat_publisher_name', 'guid']
        p['selected_extras'] = {d['key']: d['value'] for d in extras if d['key'] not in boring_fields}
        s = "<br>"
        for d in extras:
            if d['key'] not in boring_fields:
                s += "&nbsp;&nbsp;&nbsp;&nbsp;<i>{}</i>: {}<br>".format(d['key'], d['value'])
        from jinja2 import Markup
        if s == "<br>":
            s = ""
        p['selected_extras'] = Markup(s)
        #p['selected_extras'] = {d['key']: d['value'] for d in extras if d['key'] not in boring_fields}
        #[{'key': 'no_updates_on', 'value': '["Sundays","yesterday"]'}, {'key': 'temporal_coverage_join_operation', 'value': 'intersection'}, {'key': 'time_field', 'value': '{"1ad5394f-d158-46c1-9af7-90a9ef4e0ce1": "start", "f58a2f59-b2e8-4067-a7d9-bbedb7e119b0": "start"}'}]
    return p

def get_package(request):
    """
    Look up the package and return its parameters.
    """
    package_id = request.GET.get('package_id', None)
    if package_id is None:
        data = {}
        return JsonResponse(data)

    ckan = ckanapi.RemoteCKAN(get_site())
    metadata = ckan.action.package_show(id=package_id)
    resource_choices = OrderedDict([(r['name'], r['id']) for r in metadata['resources']])

    metadata = extend_package(metadata)
    data = {
        'metadata': metadata,
        'new_resource_choices': resource_choices,
        'package_metadata': injectable_formatted_html(metadata),
    }
    return JsonResponse(data)


def get_packages(site="https://data.wprdc.org"):
    ckan = ckanapi.RemoteCKAN(site) # Without specifying the apikey field value,
# the next line will only return non-private packages.
    try:
        packages = ckan.action.current_package_list_with_resources(limit=999999)
    except:
        packages = ckan.action.current_package_list_with_resources(limit=999999)
    # This is a list of all the packages with all the resources nested inside and all the current information.

    package_choices = []
    resource_choices = []
    initial_resource_choices = []
    resource_choices_by_package_id = defaultdict(list)
    resources_by_id = {}

    publishers_by_id = {}
    dataset_count_by_publisher_id = defaultdict(int)
    #non_harvested_packages = [p for p in packages if '_harvested' not in [tag['name'] for tag in p['tags']]]
    #harvested_packages = [p for p in packages if '_harvested' in [tag['name'] for tag in p['tags']]]
    non_harvested_packages = [p for p in packages if 'Esri Rest API' not in [r['name'] for r in p['resources']]]
    harvested_packages = [p for p in packages if 'Esri Rest API' in [r['name'] for r in p['resources']]]
    packages = non_harvested_packages + harvested_packages # Resort packages to push ETLed and manually uploaded packages to the top.
    for k,p in enumerate(packages):
        package_choices.append( (p['id'], p['title']) )
        publisher_id= p['organization']['id']
        dataset_count_by_publisher_id[publisher_id] += 1

        if publisher_id not in publishers_by_id:
            publishers_by_id[publisher_id] = p['organization']

        p = extend_package(p)
        for r in p['resources']:
            #r = extend_resource(r) # Does this add to the run time so much that Jinja templating
            # (e.g., % if resource.format == ''%}None{% else %}{{ resource.format }}{% endif %})
            # should be used instead in get_packages?
            resources_by_id[r['id']] = r
            choice = (r['id'], r['name'])
            resource_choices.append(choice)
            resource_choices_by_package_id[p['id']].append(choice)
            if k == 0:
                initial_resource_choices.append(choice)

    publisher_choices = []
    publisher_choices.append( ("All publishers", "All publishers ({} datasets)".format(len(packages))) )
    for publisher_id, dataset_count in sorted(dataset_count_by_publisher_id.items(), key=lambda x: (-x[1], publishers_by_id[x[0]]['name']), reverse=False): # Gives keys sorted by values.
        o = publishers_by_id[publisher_id]
        publisher_code = o['name']
        publisher_title = o['title']
        label = "{} ({} dataset{})".format(publisher_title, dataset_count, "s" if dataset_count != 1 else "")
        publisher_choice = (publisher_id, label)
        publisher_choices.append(publisher_choice)

    return packages, package_choices, resource_choices, resource_choices_by_package_id, resources_by_id, publisher_choices

def get_package_list(request):
    """
    Look up the package and return its parameters.
    """
    chosen_publisher_id = request.GET.get('publisher_id', None)
    if chosen_publisher_id == 'All publishers':
        #return redirect('/data_sprocket/') # A redirect won't work because get_package_list is an AJAX call.
        all_packages, package_choices, all_resource_choices, resource_choices_by_package_id, resources_by_id, publisher_choices = get_packages()
        package_choices = OrderedDict([ (y,x) for (x,y) in package_choices ])
        initial_package = extend_package(all_packages[0])
        resource_choices = OrderedDict([ (y,x) for (x,y) in resource_choices_by_package_id[initial_package['id']] ])
        data = { 'new_package_choices': package_choices,
                'metadata': initial_package,
                'new_resource_choices': resource_choices,
                'resource': extend_resource(all_packages[0]['resources'][0], initial_package),
                }
        return JsonResponse(data)

    ckan = ckanapi.RemoteCKAN(get_site())
    try:
        packages = ckan.action.current_package_list_with_resources(limit=999999)
    except:
        packages = ckan.action.current_package_list_with_resources(limit=999999)

    package_choices = []
    chosen_packages = []
    initial_resource_choices = []
    for k,p in enumerate(packages):
        publisher_id= p['organization']['id']
        if publisher_id == chosen_publisher_id:
            resource_count = len(p['resources'])
            package_title = p['title']
            package_label = "{} ({} resource{})".format(package_title, resource_count, "s" if resource_count != 1 else "")
            package_id = p['id']
            package_choice = (package_label, package_id)
            package_choices.append(package_choice)

            p = extend_package(p)
            chosen_packages.append(p)

    initial_package = chosen_packages[0]
    for r in initial_package['resources']:
        choice = (r['name'], r['id'])
        initial_resource_choices.append(choice)

    initial_resource = extend_resource(initial_package['resources'][0], initial_package)

    data = { 'new_package_choices': OrderedDict(package_choices),
            'metadata': initial_package,
            'package_metadata': injectable_formatted_html(initial_package),
            'resource_metadata': injectable_formatted_html(initial_resource),
            'new_resource_choices': OrderedDict(initial_resource_choices),
            'resource': initial_resource,
    }

    elapsed_time = time.process_time() - t
    ic(elapsed_time)
    return JsonResponse(data)

def format_label(p, resource_geo_fields):
    if resource_geo_fields is None or 'label_fields' not in resource_geo_fields:
        return ''
    label_fields = resource_geo_fields['label_fields']
    d = { field:p[field] for field in label_fields if field in p }
    return injectable_formatted_html(d)

def map_view(request):
    package_id = request.GET.get('package_id', None)
    resource_id = request.GET.get('map_resource_id', None)
    query = request.GET.get('query', None) # How should filters or query be parameterized/represented/serialized?

    if resource_id is None:
        context = {'msg': 'No resource ID found.'}
        return render(request, 'data_sprocket/map.html', context)
    site = get_site()
    if package_id is None:
        package_id = get_resource_parameter(site,resource_id,parameter='package_id')
    try:
        # Get the geo_fields to set the latitude and longitude columns.
        extras = get_package_parameter(site, package_id, 'extras')
        geo_fields = None
        if extras is None:
            extras = []
        for extra in extras:
            if extra['key'] == 'geo_fields':
                geo_fields = json.loads(extra['value'])
                break
        latitude_field = None
        longitude_field = None
        if geo_fields is not None:
            resource_geo_fields = geo_fields.get(resource_id)
            if resource_geo_fields is not None:
                latitude_field = geo_fields.get('latitude')
                longitude_field = geo_fields.get('longitude')
        if latitude_field is None or longitude_field is None:
            datastore_dimensions_description, rows, columns, schema = get_datastore_dimensions(site, resource_id, include_tooltip=True)
            if 'latitude' in schema and 'longitude' in schema:
                latitude_field, longitude_field = 'latitude', 'longitude'
            elif 'X' in schema and 'Y' in schema:
                latitude_field, longitude_field = 'Y', 'X'
            elif 'x' in schema and 'y' in schema:
                latitude_field, longitude_field = 'y', 'x'
            elif 'Lat' in schema and 'Lon' in schema:
                latitude_field, longitude_field = 'Lat', 'Lon'

        if latitude_field is None or longitude_field is None:
            context = {'msg': 'Unable to geolocate points. This might be because the field names do not match the expected field names for laatitude and longitude data.'}
            return render(request, 'data_sprocket/map.html', context)
        # Construct a query to get points to plot.
        max_points = 500
        query = 'SELECT "{}" AS latitude, "{}" as longitude, * FROM "{}" LIMIT {}'.format(latitude_field, longitude_field, resource_id, max_points)
        points_from_query = query_resource(site, query)
        points = [{'coords': [p[latitude_field], p[longitude_field]], 'formatted_label': format_label(p, resource_geo_fields)} for p in points_from_query if p[latitude_field] is not None and p[longitude_field] is not None]
        msg = 'map_view thinks that the latitude and longitude fields are {} and {}. '.format(latitude_field, longitude_field)
        if rows > max_points:
            msg += '<br><b>NOTE:</b> The map is limited to {} points, so {} points are not being displayed.'.format(max_points, rows - max_points)

        # [ ] TO DO: Optionally style map based on other features/fields of the data.
        # [ ] Eventually add support for mapping other formats like GeoJSON/KML/maybe even SHP. Leaflet has an extension that enables this.
        # [ ] Add support for mapping stealth-geocoded stuff (e.g., datastores with the _the_geom field).
        context = {
            'points': points,
            'rows': rows,
            'columns': columns,
            'msg': msg
        }
    except ckanapi.errors.NotFound: # if there's no datastore for this resource ID.
        context = {'msg': 'No datastore found for resource ID {}'.format(resource_id)}
    return render(request, 'data_sprocket/map.html', context)

def index(request):
    all_packages, package_choices, all_resource_choices, resource_choices_by_package_id, resources_by_id, publisher_choices = get_packages()
    initial_package_id = package_choices[0][0]
    initial_resource_choices = resource_choices_by_package_id[initial_package_id]
    initial_resource_id = initial_resource_choices[0][0]
    initial_package = extend_package(all_packages[0])
    initial_resource = extend_resource(resources_by_id[initial_resource_id], initial_package)
    if initial_resource['datastore_active']:
        site = get_site()
        datastore_dimensions_description, rows, columns, schema = get_datastore_dimensions(site, initial_resource_id, include_tooltip=True)

        initial_datastore = { 'rows': rows,
            'columns': columns,
            'dimensions': datastore_dimensions_description}
    else:
        initial_datastore = None

    class DatasetForm(forms.Form):
        publisher = forms.ChoiceField(choices=publisher_choices, widget=forms.Select(attrs={'autocomplete':'off'})) # Adding these autocomplete:off attrs is a hack to get around this
        package = forms.ChoiceField(choices=package_choices, widget=forms.Select(attrs={'autocomplete':'off'})) # Firefox bug/feature wherewhere it does not use the "selected" option
        # when reloading the page. Instead, it maintains the last chosen value. Firefox developers prefer this functionality. It can be overridden with Command-Shift-R reloading.
        # https://stackoverflow.com/questions/1479233/why-doesnt-firefox-show-the-correct-default-select-option/8258154#8258154
        resource = forms.ChoiceField(choices=initial_resource_choices, widget=forms.Select(attrs={'autocomplete':'off'})) # Limit to resource per package

    dataset_form = DatasetForm(initial = {'package': initial_package_id, 'resource': initial_resource_id})
    context = { 'dataset_form': dataset_form,
            'packages': all_packages,
            'metadata': all_packages[0],
            'resource': initial_resource,
            'datastore': initial_datastore,
        }

    return render(request, 'data_sprocket/index.html', context)
