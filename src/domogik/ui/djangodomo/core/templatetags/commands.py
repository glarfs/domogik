#!/usr/bin/python
# -*- coding: utf-8 -*-

""" This file is part of B{Domogik} project (U{http://www.domogik.org}).

License
=======

B{Domogik} is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

B{Domogik} is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Domogik. If not, see U{http://www.gnu.org/licenses}.


@author: Domogik project
@copyright: (C) 2007-2010 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

from django import template
from django.template import Node
from djangodomo.core.models import DeviceTypes, DeviceUsages
from htmlentitydefs import name2codepoint
import re
import simplejson

register = template.Library()

def unescape(s):
    "unescape HTML code refs; c.f. http://wiki.python.org/moin/EscapingHtml"
    return re.sub('&(%s);' % '|'.join(name2codepoint),
              lambda m: unichr(name2codepoint[m.group(1)]), s)

class GetCommandBinary(Node):
    @staticmethod
    def get_script(feature, device_type, device_usage, parameters_type, parameters_usage):
        script = """$('#command_%s_%s').binary_command({
                        usage: %s,
                        value0: '%s',
                        value1: '%s',
                        text0: '%s',
                        text1: '%s',
                        action: function(self, value) {
                            $.getREST(['command', '%s', '%s', value],
                                function(data) {
                                    var status = (data.status).toLowerCase();
                                    if (status == 'ok') {
                                        self.valid(%s);
                                    } else {
                                        /* Error */
                                        self.cancel();
                                    }
                                }
                            );
                        }
                    })
                        .binary_command('setState', 'Off');
                    """ % (feature.device_id, feature.device_type_feature_id, feature.device.device_usage_id,
                           parameters_type['value0'], parameters_type['value1'],
                           parameters_usage['binary']['state0'], parameters_usage['binary']['state1'],
                           device_type.device_technology_id, feature.device.address, feature.device_type_feature.return_confirmation)
        return script

class GetCommandRange(Node):
    @staticmethod
    def get_script(feature, device_type, device_usage, parameters_type, parameters_usage):
        script = """$("#command_%s_%s").range_command({
                        usage: %s,
                        min_value: %s,
                        max_value: %s,
                        step: %s,
                        unit: '%s',
                        action: function(self, value) {
                            $.getREST(['command', '%s', '%s', '%s', value],
                                function(data) {
                                    var status = (data.status).toLowerCase();
                                    if (status == 'ok') {
                                        self.valid(%s);
                                    } else {
                                        /* Error */
                                        self.cancel();
                                    }
                                }
                            );
                        }
                    })
                        .range_command('setValue', 50);
                    """ % (feature.device_id, feature.device_type_feature_id, feature.device.device_usage_id,
                           parameters_type['valueMin'], parameters_type['valueMax'],
                           parameters_usage['range']['step'], parameters_usage['range']['unit'],
                           device_type.device_technology_id, feature.device.address,
                           parameters_type['command'], feature.device_type_feature.return_confirmation)
        return script

class GetCommandTrigger():
    @staticmethod
    def get_script(feature, device_type, device_usage, parameters_type, parameters_usage):
        script = """$('#command_%s_%s').trigger_command({
                        usage: %s,
                        action: function(self) {
                            $.getREST(['command', '%s', '%s', '%s'],
                                function(data) {
                                    var status = (data.status).toLowerCase();
                                    if (status == 'ok') {
                                        self.valid(%s);
                                    } else {
                                        /* Error */
                                        self.cancel();
                                    }
                                }
                            );
                        }
                    });
                    """ % (feature.device_id, feature.device_type_feature_id, feature.device.device_usage_id,
                           device_type.device_technology_id, feature.device.address,
                           parameters_type['command'], feature.device_type_feature.return_confirmation)
        return script

class GetCommand(Node):
    def __init__(self, feature):
        self.feature = template.Variable(feature)

    def render(self, context):
        feature = self.feature.resolve(context)
        device_type = DeviceTypes.get_dict_item(feature.device.device_type_id)
        device_usage = DeviceUsages.get_dict_item(feature.device.device_usage_id)
        parameters_type = simplejson.loads(unescape(feature.device_type_feature.parameters))
        parameters_usage = simplejson.loads(unescape(device_usage.default_options))
        print parameters_type
        print parameters_usage
        if feature.device_type_feature.value_type == "binary":
            script = GetCommandBinary.get_script(feature, device_type, device_usage, parameters_type, parameters_usage)
        if feature.device_type_feature.value_type == "range":
            script = GetCommandRange.get_script(feature, device_type, device_usage, parameters_type, parameters_usage)
        if feature.device_type_feature.value_type == "trigger":
            script = GetCommandTrigger.get_script(feature, device_type, device_usage, parameters_type, parameters_usage)
            
        return script
    
def do_get_command(parser, token):
    """
    This returns the jquery function for creating a command button.

    Usage::

        {% get_command feature %}
    """
    args = token.contents.split()
    if len(args) != 2:
        raise TemplateSyntaxError, "'get_command' requires 'feature' argument"
    return GetCommand(args[1])

register.tag('get_command', do_get_command)