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

Base class for all xPL clients

Implements
==========

- XplPlugin
- XplResult

@author: Maxence Dunnewind <maxence@dunnewind.net>
@copyright: (C) 2007-2012 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

import signal
import threading
import os
import sys
from domogik.xpl.common.xplconnector import XplMessage, Manager, Listener
from domogik.xpl.common.baseplugin import BasePlugin
from domogik.common.configloader import Loader, CONFIG_FILE
from domogik.common.processinfo import ProcessInfo
from domogik.mq.pubsub.publisher import MQPub
from domogik.mq.reqrep.worker import MQRep
from domogik.mq.message import MQMessage
from zmq.eventloop.ioloop import IOLoop
import zmq


# clients (plugins, etc) status
STATUS_UNKNOWN = "unknown"
STATUS_STARTING = "starting"
STATUS_ALIVE = "alive"
STATUS_STOP_REQUEST = "stop-request"
STATUS_STOPPED = "stopped"
STATUS_DEAD = "dead"
STATUS_INVALID = "invalid"

# folder for the packages in package_path folder (/var/lib/domogik/)
PACKAGES_DIR = "packages"

# domogik vendor id (for xpl)
DMG_VENDOR_ID = "domogik"

# time between each read of cpu/memory usage for process
TIME_BETWEEN_EACH_PROCESS_STATUS = 60

class XplPlugin(BasePlugin, MQRep):
    '''
    Global plugin class, manage signal handlers.
    This class shouldn't be used as-it but should be extended by xPL plugin
    This class is a Singleton
    '''
    def __init__(self, name, stop_cb = None, is_manager = False, reload_cb = None, dump_cb = None, parser = None,
                 daemonize = True, nohub = False):
        '''
        Create XplPlugin instance, which defines system handlers
        @param name : The name of the current plugin
        @param stop_cb : Additionnal method to call when a stop request is received
        @param is_manager : Must be True if the child script is a Domogik Manager process
        You should never need to set it to True unless you develop your own manager
        @param reload_cb : Callback to call when a "RELOAD" order is received, if None,
        nothing will happen
        @param dump_cb : Callback to call when a "DUMP" order is received, if None,
        nothing will happen
        @param parser : An instance of OptionParser. If you want to add extra options to the generic option parser,
        create your own optionparser instance, use parser.addoption and then pass your parser instance as parameter.
        Your options/params will then be available on self.options and self.args
        @param daemonize : If set to False, force the instance *not* to daemonize, even if '-f' is not passed
        on the command line. If set to True (default), will check if -f was added.
        @param nohub : if set the hub discovery will be disabled
        '''
        BasePlugin.__init__(self, name, stop_cb, parser, daemonize)
        Watcher(self)
        self.log.info("----------------------------------")
        self.log.info("Starting plugin '%s' (new manager instance)" % name)
        self._name = name

        # MQ publisher and REP
        self._zmq = zmq.Context()
        self._pub = MQPub(self._zmq, self._name)
        self._pub.send_event('plugin', 
                             {"type" : "plugin",
                              "id" : self._name,
                              "event" : STATUS_STARTING})
        ### MQ
        # for stop requests
        MQRep.__init__(self, self._zmq, self._name)


        self._is_manager = is_manager
        cfg = Loader('domogik')
        my_conf = cfg.load()
        self._config_files = CONFIG_FILE
        config = dict(my_conf[1])

        # Get pid and write it in a file
        self._pid_dir_path = config['pid_dir_path']
        self._get_pid()

        if len(self.get_sanitized_hostname()) > 16:
            self.log.error("You must use 16 char max hostnames ! %s is %s long" % (self.get_sanitized_hostname(), len(self.get_sanitized_hostname())))
            self.force_leave()
            return

        if 'broadcast' in config:
            broadcast = config['broadcast']
        else:
            broadcast = "255.255.255.255"
        if 'bind_interface' in config:
            self.myxpl = Manager(config['bind_interface'], broadcast = broadcast, plugin = self, nohub = nohub)
        else:
            self.myxpl = Manager(broadcast = broadcast, plugin = self, nohub = nohub)

        # TODO : remove
        #self._l = Listener(self._system_handler, self.myxpl, {'schema' : 'domogik.system',
        #                                                       'xpltype':'xpl-cmnd'})

        self._reload_cb = reload_cb
        self._dump_cb = dump_cb

        # Create object which get process informations (cpu, memory, etc)
        # TODO : activate
        #self._process_info = ProcessInfo(os.getpid(),
        #                                 TIME_BETWEEN_EACH_PROCESS_STATUS,
        #                                 self._send_process_info,
        #                                 self.log,
        #                                 self.myxpl)
        #self._process_info.start()

        self.enable_hbeat_called = False

        self.log.debug("end single xpl plugin")

    def ready(self):
        """ to call at the end of the __init__ of classes that inherits of XplPlugin
        """
        ### activate xpl hbeat
        if self.enable_hbeat_called == True:
            self.log.error("in ready() : enable_hbeat() function already called : the plugin may not be fully converted to the 0.4+ Domogik format")
        else:
            self.enable_hbeat()

        ### send plugin status : STATUS_ALIVE
        # TODO : why the dbmgr has no self.name defined ???????
        # temporary set as unknown to avoir blocking bugs
        if not hasattr(self, '_name'):
            self.name = "unknown"
        self._pub.send_event('plugin', 
                             {"type" : "plugin",
                              "id" : self._name,
                              "event" : STATUS_ALIVE})

        ### Instantiate the MQ
        # nothing can be launched after this line (blocking call!!!!)
        self.log.info("Start IOLoop for MQ : nothing else can be executed in the __init__ after this! Make sure that the self.ready() call is the last line of your init!!!!")
        IOLoop.instance().start()


    def on_mdp_request(self, msg):
        """ Handle Requests over MQ
            @param msg : MQ req message
        """
        self.log.debug("MQ Request received : {0}" . format(str(msg)))

        ### stop the plugin
        if msg._action == "plugin.stop.do":
            self.log.info("Plugin stop request : {0}".format(msg))
            self._mdp_reply_plugin_stop(msg)

    def _mdp_reply_plugin_stop(self, data):
        """ Stop the plugin
            @param data : MQ req message

            First, send the MQ Rep to 'ack' the request
            Then, change the plugin status to STATUS_STOP_REQUEST
            Then, quit the plugin by calling force_leave(). This should make the plugin send a STATUS_STOPPED if all is ok

            Notice that no check is done on the MQ req content : we need nothing in it as it is directly addressed to a plugin
        """
        ### Send the ack over MQ Rep
        msg = MQMessage()
        msg.set_action('plugin.stop.result')
        status = True
        reason = ""
        msg.add_data('status', status)
        msg.add_data('reason', reason)
        self.reply(msg.get())

        ### Change the plugin status
        self._pub.send_event('plugin', 
                             {"type" : "plugin",
                              "id" : self._name,
                              "event" : STATUS_STOP_REQUEST})

        ### Try to stop the plugin
        # if it fails, the manager should try to kill the plugin
        self.force_leave()


    def send_stopped_status(self):
        """ Send the STATUS_STOPPED status over the MQ
        """ 
        if hasattr(self, "_pub"):
            self._pub.send_event('plugin', 
                                 {"type" : "plugin",
                                  "id" : self._name,
                                  "event" : STATUS_STOPPED})

    def get_config_files(self):
       """ Return list of config files
       """
       return self._config_files

    def get_data_files_directory(self):
       """
       Return the directory where a plugin developper can store data files.
       If the directory doesn't exist, try to create it.
       After that, try to create a file inside it.
       If something goes wrong, generate an explicit exception.
       """
       cfg = Loader('domogik')
       my_conf = cfg.load()
       config = dict(my_conf[1])
       path = "{0}/{1}/{2}_{3}/data/" % (config['package_path'], PACKAGES_DIR, "plugin", self._name)
       if os.path.exists(path):
           if not os.access(path, os.W_OK & os.X_OK):
               raise OSError("Can't write in directory %s" % path)
       else:
           try:
               os.mkdir(path, 0770)
               self.log.info("Create directory %s." % path)
           except:
               raise OSError("Can't create directory %s." % path)
       try:
           tmp_prefix = "write_test";
           count = 0
           filename = os.path.join(path, tmp_prefix)
           while(os.path.exists(filename)):
               filename = "{}.{}".format(os.path.join(path, tmp_prefix),count)
               count = count + 1
           f = open(filename,"w")
           f.close()
           os.remove(filename)
       except :
           raise IOError("Can't create a file in directory %s." % path)
       return path

    # TODO :remove
    #def get_stats_files_directory(self):
    #   """ Return the directory where a plugin developper can store data files
    #   """
    #   cfg = Loader('domogik')
    #   my_conf = cfg.load()
    #   config = dict(my_conf[1])
    #   if config.has_key('package_path'):
    #       path = "%s/domogik_packages/stats/%s" % (config['package_path'], self._name)
    #   else:
    #       path = "%s/share/domogik/stats/%s" % (config['src_prefix'], self._name)
    #   return path

    def enable_hbeat(self, lock = False):
        """ Wrapper for xplconnector.enable_hbeat()
        """
        self.myxpl.enable_hbeat(lock)
        self.enable_hbeat_called = True

    def _send_process_info(self, pid, data):
        """ Send process info (cpu, memory) on xpl
            @param : process pid
            @param data : dictionnary of process informations
        """
        mess = XplMessage()
        mess.set_type("xpl-stat")
        mess.set_schema("domogik.usage")
        mess.add_data({"name" : "%s.%s" % (self.get_plugin_name(), self.get_sanitized_hostname()),
                       "pid" : pid,
                       "cpu-percent" : data["cpu_percent"],
                       "memory-percent" : data["memory_percent"],
                       "memory-rss" : data["memory_rss"],
                       "memory-vsz" : data["memory_vsz"]})
        self.myxpl.send(mess)

    def _get_pid(self):
        """ Get current pid and write it to a file
        """
        pid = os.getpid()
        pid_file = os.path.join(self._pid_dir_path,
                                self._name + ".pid")
        self.log.debug("Write pid file for pid '%s' in file '%s'" % (str(pid), pid_file))
        fil = open(pid_file, "w")
        fil.write(str(pid))
        fil.close()

    # TODO : remove
    #def _system_handler(self, message):
    #    """ Handler for domogik system messages
    #    """
    #    cmd = message.data['command']
    #    if not self._is_manager and cmd in ["stop", "reload", "dump"]:
    #        self._client_handler(message)
    #    else:
    #        self._manager_handler(message)

    # TODO : remove
    #def _client_handler(self, message):
    #    """ Handle domogik system request for an xpl client
    #    @param message : the Xpl message received
    #    """
    #    try:
    #        cmd = message.data["command"]
    #        plugin = message.data["plugin"]
    #        host = message.data["host"]
    #        if host != self.get_sanitized_hostname():
    #            return
    #    except KeyError as e:
    #        self.log.error("command, plugin or host key does not exist : %s", e)
    #        return
    #    if cmd == "stop" and plugin in ['*', self.get_plugin_name()]:
    #        self.log.info("Someone asked to stop %s, doing." % self.get_plugin_name())
    #        self._answer_stop()
    #        self.force_leave()
    #    elif cmd == "reload":
    #        if self._reload_cb is None:
    #            self.log.info("Someone asked to reload config of %s, but the plugin \
    #            isn't able to do it." % self.get_plugin_name())
    #        else:
    #            self._reload_cb()
    #    elif cmd == "dump":
    #        if self._dump_cb is None:
    #            self.log.info("Someone asked to dump config of %s, but the plugin \
    #            isn't able to do it." % self.get_plugin_name())
    #        else:
    #            self._dump_cb()
    #    else: #Command not known
    #        self.log.info("domogik.system command not recognized : %s" % cmd)

    def __del__(self):
        if hasattr(self, "log"):
            self.log.debug("__del__ Single xpl plugin")
            # we guess that if no "log" is defined, the plugin has not really started, so there is no need to call force leave (and _stop, .... won't be created)
            self.force_leave()

    # TODO : remove
    #def _answer_stop(self):
    #    """ Ack a stop request
    #    """
    #    mess = XplMessage()
    #    mess.set_type("xpl-trig")
    #    mess.set_schema("domogik.system")
    #    #mess.add_data({"command":"stop", "plugin": self.get_plugin_name(),
    #    #    "host": self.get_sanitized_hostname()})
    #    mess.add_data({"command":"stop", 
    #                   "host": self.get_sanitized_hostname(),
    #                   "plugin": self.get_plugin_name()})
    #    self.myxpl.send(mess)

    def _send_hbeat_end(self):
        """ Send the hbeat.end message
        """
        if hasattr(self, "myxpl"):
            mess = XplMessage()
            mess.set_type("xpl-stat")
            mess.set_schema("hbeat.end")
            self.myxpl.send(mess)

    def _manager_handler(self, message):
        """ Handle domogik system request for the Domogik manager
        @param message : the Xpl message received
        """

    def wait(self):
        """ Wait until someone ask the plugin to stop
        """
        self.myxpl._network.join()

    def force_leave(self):
        '''
        Leave threads & timers
        '''
        if hasattr(self, "log"):
            self.log.debug("force_leave called")
        # send stopped status over the MQ
        self.send_stopped_status()
        # send hbeat.end message
        self._send_hbeat_end()
        self.get_stop().set()
        for t in self._timers:
            if hasattr(self, "log"):
                self.log.debug("Try to stop timer %s"  % t)
            t.stop()
            if hasattr(self, "log"):
                self.log.debug("Timer stopped %s" % t)
        for cb in self._stop_cb:
            if hasattr(self, "log"):
                self.log.debug("Calling stop additionnal method : %s " % cb.__name__)
            cb()
        for t in self._threads:
            if hasattr(self, "log"):
                self.log.debug("Try to stop thread %s" % t)
            try:
                t.join()
            except RuntimeError:
                pass
            if hasattr(self, "log"):
                self.log.debug("Thread stopped %s" % t)
            #t._Thread__stop()
        #Finally, we try to delete all remaining threads
        for t in threading.enumerate():
            if t != threading.current_thread() and t.__class__ != threading._MainThread:
                if hasattr(self, "log"):
                    self.log.info("The thread %s was not registered, killing it" % t.name)
                t.join()
                if hasattr(self, "log"):
                    self.log.info("Thread %s stopped." % t.name)
        if threading.activeCount() > 1:
            if hasattr(self, "log"):
                self.log.warn("There are more than 1 thread remaining : %s" % threading.enumerate())


class XplResult():
    '''
    This object just provides a way to get and set a value between threads
    '''

    def __init__(self):
        self.value = None
        self.event = threading.Event()

    def set_value(self, value):
        '''
        Set the new value of the objet
        '''
        self.value = value

    def get_value(self):
        '''
        Get the value of the objet
        '''
        return self.value

    def get_lock(self):
        '''
        Returns an event item
        '''
        return self.event


class Watcher:
    """this class solves two problems with multithreaded
    programs in Python, (1) a signal might be delivered
    to any thread (which is just a malfeature) and (2) if
    the thread that gets the signal is waiting, the signal
    is ignored (which is a bug).

    The watcher is a concurrent process (not thread) that
    waits for a signal and the process that contains the
    threads.  See Appendix A of The Little Book of Semaphores.
    http://greenteapress.com/semaphores/

    I have only tested this on Linux.  I would expect it to
    work on the Macintosh and not work on Windows.
    Tip found at http://code.activestate.com/recipes/496735/
    """

    def __init__(self, plugin):
        """ Creates a child thread, which returns.  The parent
            thread waits for a KeyboardInterrupt and then kills
            the child thread.
        """
        self.child = os.fork()
        if self.child == 0:
            return
        else:
            self._plugin = plugin
            self._plugin.log.debug("watcher fork")
            signal.signal(signal.SIGTERM, self._signal_handler)
            self.watch()

    def _signal_handler(self, signum, frame):
        """ Handler called when a SIGTERM is received
        Stop the plugin
        """
        self._plugin.log.info("SIGTERM receive, stop plugin")
        self._plugin.force_leave()
        self.kill()

    def watch(self):
        try:
            os.wait()
        except KeyboardInterrupt:
            print('KeyBoardInterrupt')
            self._plugin.log.info("Keyoard Interrupt detected, leave now.")
            self._plugin.force_leave()
            self.kill()
        except OSError:
            print("OSError")
        sys.exit()

    def kill(self):
        try:
            os.kill(self.child, signal.SIGKILL)
        except OSError: pass
