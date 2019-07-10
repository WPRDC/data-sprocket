from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django import forms
import ckanapi
from collections import defaultdict, OrderedDict
from pprint import pprint, pformat

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

def extend_resource(r):
    if 'format' not in r or r['format'] == '':
        r['format'] = 'None'
    if 'datastore_active' not in r or not r['datastore_active']:
        r['datastore_active'] = 'False'
    else:
        r['datastore_active'] = 'True'

    r['download_link_exists'] = False
    r['external_link_exists'] = False
    if 'url' in r:
        if 'data.wprdc.org' in r['url']:
            r['download_link_exists'] = True
        else:
            r['external_link_exists'] = True

    return r

def injectable_pprint_html(d):
    return "<pre>{}</pre>".format(pformat(d))

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
        'resource_metadata': injectable_pprint_html(metadata),

    }
    return JsonResponse(data)

def extend_package(p):
    p['plain_tags'] = ', '.join(extract_tags(p))
    p['dataset_url'] = get_site() + "/dataset/" + p['name']
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
        'package_metadata': injectable_pprint_html(metadata),
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
    for publisher_id in sorted(dataset_count_by_publisher_id, key=dataset_count_by_publisher_id.get, reverse=True): # Gives keys sorted by values.
        o = publishers_by_id[publisher_id]
        publisher_code = o['name']
        publisher_title = o['title']
        dataset_count = dataset_count_by_publisher_id[publisher_id]
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
        initial_package = all_packages[0]
        resource_choices = OrderedDict([ (y,x) for (x,y) in resource_choices_by_package_id[initial_package['id']] ])
        data = { 'new_package_choices': package_choices,
                'metadata': initial_package,
                'new_resource_choices': resource_choices,
                'resource': extend_resource(all_packages[0]['resources'][0]),
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

            package_choices.append( (p['title'], p['id']) )

            p = extend_package(p)
            chosen_packages.append(p)

    initial_package = chosen_packages[0]
    for r in initial_package['resources']:
        choice = (r['name'], r['id'])
        initial_resource_choices.append(choice)

    initial_resource = extend_resource(initial_package['resources'][0])

    data = { 'new_package_choices': OrderedDict(package_choices),
            'metadata': initial_package,
            'package_metadata': injectable_pprint_html(initial_package),
            'resource_metadata': injectable_pprint_html(initial_resource),
            'new_resource_choices': OrderedDict(initial_resource_choices),
            'resource': initial_resource,
    }
    return JsonResponse(data)


def index(request):
    all_packages, package_choices, all_resource_choices, resource_choices_by_package_id, resources_by_id, publisher_choices = get_packages()
    initial_package_id = package_choices[0][0]
    initial_resource_choices = resource_choices_by_package_id[initial_package_id]
    initial_resource_id = initial_resource_choices[0][0]
    initial_resource = extend_resource(resources_by_id[initial_resource_id])
    class DatasetForm(forms.Form):
        publisher = forms.ChoiceField(choices=publisher_choices)
        package = forms.ChoiceField(choices=package_choices)
        resource = forms.ChoiceField(choices=initial_resource_choices) # Limit to resource per package

    dataset_form = DatasetForm(initial = {'package': initial_package_id, 'resource': initial_resource_id})
    context = { 'dataset_form': dataset_form,
            'packages': all_packages,
            'metadata': all_packages[0],
            'resource': initial_resource,
            'initial_download_opacity': 1 if initial_resource['download_link_exists'] else 0,
            'initial_link_opacity': 1 if initial_resource['external_link_exists'] else 0,
        }

    return render(request, 'data_sprocket/index.html', context)
