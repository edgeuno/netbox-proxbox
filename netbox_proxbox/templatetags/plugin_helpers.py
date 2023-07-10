from django import template
from django.apps import apps
from django.urls import NoReverseMatch, reverse

from extras.plugins import PluginConfig
from utilities.forms import TableConfigForm

register = template.Library()


def _resolve_namespace(instance):
    """
    Get the appropriate namespace for the app based on whether it is a Plugin or base application
    """

    app = apps.get_app_config(instance._meta.app_label)
    if isinstance(app, PluginConfig):
        return f'plugins:{app.label}'
    return f'{app.label}'


def _get_plugin_viewname(instance, action=None):
    """
    Return the appropriate viewname for adding, editing, viewing changelog or deleting an instance.
    """

    # Validate action
    assert action in ('add', 'edit', 'delete', 'list', 'changelog', 'multi_add')
    app_label = _resolve_namespace(instance)
    print(f'{app_label}')
    if action is not None:
        viewname = f'{app_label}:{instance._meta.model_name}_{action}'
    else:
        viewname = f'{app_label}:{instance._meta.model_name}'
    print(f'{app_label}:{viewname}')
    return viewname


@register.filter()
def validated_plugin_viewname(model, action):
    """
    Return the view name for the given model and action if valid, or None if invalid.
    """
    namespace = _resolve_namespace(model)
    if action:
        viewname = f'{namespace}:{model._meta.model_name}_{action}'
    else:
        viewname = f'{namespace}:{model._meta.model_name}'

    try:
        # Validate and return the view name. We don't return the actual URL yet because many of the templates
        # are written to pass a name to {% url %}.
        # reverse(viewname)
        return viewname
    except NoReverseMatch:
        return None


@register.filter()
def get_model_params(model):
    l = []
    try:
        if model.get_fields_to_show():
            l = model.get_fields_to_show()
    except Exception:
        print('')
        l = []
    if len(l) < 1:
        l = [f.name for f in model._meta.get_fields()]
    try:
        if model.get_extra_params():
            l.extend(model.get_extra_params())
    except Exception as N:
        print('No extras found')
    return l


@register.filter()
def get_model_value(model, param):
    c = ''
    try:
        c = eval(f'model.{param}')
    except Exception as N:
        print('No parameter found')
        c = '******$$$$$******'
    return c


@register.filter()
def get_custom_title(model):
    try:
        return model.get_custom_title()
    except NoReverseMatch:
        return None


@register.filter()
def get_model_title(model):
    try:
        return model.get_model_title()
    except Exception:
        return None


@register.filter()
def get_verbose_name(obj, attr):
    value = attr
    fields = getattr(obj._meta, 'fields', [])
    for x in fields:
        if x.attname == attr:
            value = x.verbose_name
            break
    output = ' '.join([w[0].upper() + w[1:] for w in value.split()])
    return output


@register.simple_tag
def get_proper_elided_page_range(table, on_each_side=3, on_ends=2):
    paginator = table.paginator
    return paginator.get_elided_page_range(number=table.page.number,
                                           on_each_side=on_each_side,
                                           on_ends=on_ends)



