from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django import forms
import ckanapi
from collections import defaultdict, OrderedDict
from pprint import pprint

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

def summarize_notes(metadata):
    if 'notes' not in metadata or len(metadata['notes']) == 0:
        return "[No notes]"
    return metadata['notes'][0:40] + " ..."

def extract_tags(metadata):
    return [t['name'] for t in metadata['tags']]

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

    data = {
        'resource': metadata,
    }
    return JsonResponse(data)

def extend_package(p):
    p['plain_tags'] = ', '.join(extract_tags(p))
    p['notes_summary'] = summarize_notes(p)
    p['dataset_url'] = get_site() + "/dataset/" + p['name']
    return p

def get_package(request):
    """
    Look up the package and return its parameters.
    """
    package_id = request.GET.get('package_id', None)
    print("get_package: {}".format(package_id))
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
    for k,p in enumerate(packages):
        package_choices.append( (p['id'], p['title']) )
        p = extend_package(p)
        for r in p['resources']:
            resources_by_id[r['id']] = r
            choice = (r['id'], r['name'])
            resource_choices.append(choice)
            resource_choices_by_package_id[p['id']].append(choice)
            if k == 0:
                initial_resource_choices.append(choice)

    return packages, package_choices, resource_choices, resource_choices_by_package_id, resources_by_id

def index(request):
    all_packages, package_choices, all_resource_choices, resource_choices_by_package_id, resources_by_id = get_packages()
    initial_package_id = package_choices[0][0]
    initial_resource_choices = resource_choices_by_package_id[initial_package_id]
    initial_resource_id = initial_resource_choices[0][0]

    class DatasetForm(forms.Form):
        package = forms.ChoiceField(choices=package_choices)
        resource = forms.ChoiceField(choices=initial_resource_choices) # Limit to resource per package

    dataset_form = DatasetForm(initial = {'package': initial_package_id, 'resource': initial_resource_id})
    context = { 'dataset_form': dataset_form,
            'packages': all_packages,
            'metadata': all_packages[0],
            'resource': resources_by_id[initial_resource_id],
        }

    return render(request, 'data_sprocket/index.html', context)
