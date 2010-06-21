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

Plugin purpose
==============

Get informations about one wire network

Implements
==========

TODO

@author: Fritz SMH <fritz.smh@gmail.com>
@copyright: (C) 2007-2009 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

import ow
import time
import threading



class OneWireException:
    """
    OneWire exception
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.repr(self.value)



class ComponentDs18b20:
    """
    DS18B20 support
    """

    def __init__(self, log, onewire, interval, callback):
        """
        Return temperature each <interval> seconds
        @param log : log instance
        @param onewire : onewire network object
        @param interval : interval between each data sent
        @param callback : callback to return values
        """
        self._log = log
        self.onewire = onewire
        self.interval = interval
        self.callback = callback
        self.root = self.onewire.get_root()
        self.old_temp = {}
        self.start_listening()

    def start_listening(self):
        """ 
        Start listening for onewire ds18b20
        """
        while True:
            for comp in self.root.find(type = "DS18B20"):
                id = comp.id
                temperature = float(comp.temperature)
                if hasattr(self.old_temp, id) == False or temperature != self.old_temp[id]:
                    type = "xpl-trig"
                else:
                    type = "xpl-stat"
                self.old_temp[id] = temperature
                print "type=%s, id=%s, temp=%s" % (type, id, temperature)
                self.callback(type, {"device" : id,
                                     "type" : "temp",
                                     "current" : comp.temperature})
            time.sleep(self.interval)


class ComponentDs2401:
    """
    DS2401 support
    """

    def __init__(self, log, onewire, interval, callback):
        """
        Check component presence each <interval> seconds
        @param log : log instance
        @param onewire : onewire network object
        @param interval : interval between each data sent
        @param callback : callback to return values
        """
        self._log = log
        self.onewire = onewire
        self.interval = interval
        self.callback = callback
        self.root = self.onewire.get_root()
        self.old_present = {}
        self.start_listening()

    def start_listening(self):
        """ 
        Start listening for onewire ds2401
        """
        while True:
            for comp in self.root.find(type = "DS2401"):
                id = comp.id
                present = int(comp.present)
                if hasattr(self.old_present, id) == False or present != self.old_present[id]:
                    if present == 1:
                        status = "HIGH"
                    else:
                        status = "LOW"
                    print "id=%s, status=%s" % (id, status)
                    self.callback("xpl-trig", {"device" : id,
                                         "type" : "input",
                                         "current" : "HIGH"})
                    self.old_present[id] = present
            time.sleep(self.interval)
    

class OneWireNetwork:
    """
    Get informations about 1wire network
    """

    def __init__(self, log, dev = 'u', cache = False):
        """
        Create OneWire instance, allowing to use OneWire Network
        @param dev : device where the interface is connected to,
        default 'u' for USB
        """
        self._log = log
        try:
            ow.init(dev)
            self._cache = cache
            if cache == True:
                self._root = ow.Sensor('/')
            else:
                self._root = ow.Sensor('/uncached')
        except:
            raise OneWireException("Can't access device")


    def get_root(self):
        """
        Getter for self._root
        """
        return self._root 

