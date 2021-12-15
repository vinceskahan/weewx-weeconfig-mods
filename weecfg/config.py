#
#    Copyright (c) 2009-2020 Tom Keffer <tkeffer@gmail.com> and
#                            Matthew Wall
#
#    See the file LICENSE.txt for your full rights.
#
"""Utilities for managing the config file"""

from __future__ import print_function
from __future__ import absolute_import
import sys

import configobj

import weecfg
import weewx
from weecfg import Logger

# The default station information:
stn_info_defaults = {
    'location' : "My Home Town",
    'latitude' : "0.0",
    'longitude': "0.0",
    'altitude': "0, meter",
    'units': 'metricwx',
    'register_this_station': 'false',
    'station_type': 'Simulator',
    'driver': 'weewx.drivers.simulator',
}


class ConfigEngine(object):
    """Install, upgrade, or reconfigure the configuration file, weewx.conf"""

    def __init__(self, logger=None):
        self.logger = logger or Logger()

    def run(self, args, options):
        if options.version:
            print(weewx.__version__)
            sys.exit(0)

        if options.list_drivers:
            weecfg.print_drivers()
            sys.exit(0)

        # this is so later on we'll construct the config_dict
        skin_option_count = sum([options.list_skins is not None,
                                options.enable_skin is not None,
                                options.disable_skin is not None])
        if skin_option_count > 1:
            # There must be one, and only one, of options list/enable/disable skin(s)
            sys.exit("Must specify one and only one of --list-skins, --enable-skin, or --disable-skin.")
        elif skin_option_count == 1:
            # skip install/upgrade/reconfigure check below
            pass
        else:
            #
            # If we got to this point, the verb must be --install, --upgrade, or --reconfigure.
            # Check for errors in the options.
            #

            # There must be one, and only one, of options install, upgrade, and reconfigure
            if sum([options.install is not None,
                options.upgrade is not None,
                options.reconfigure is not None]) != 1:
                sys.exit("Must specify one and only one of --install, --upgrade, or --reconfigure.")

        # Check for missing --dist-config
        if (options.install or options.upgrade) and not options.dist_config:
            sys.exit("The commands --install and --upgrade require option --dist-config.")

        # Check for missing config file
        if options.upgrade and not (options.config_path or args):
            sys.exit("The command --upgrade requires an existing configuration file.")

        if options.install and not options.output:
            sys.exit("The --install command requires option --output.")

        # The install option does not take an old config file
        if options.install and (options.config_path or args):
            sys.exit("A configuration file cannot be used with the --install command.")

        #
        # Now run the commands.
        #

        # First, fiddle with option --altitude to convert it into a list:
        if options.altitude:
            options.altitude = options.altitude.split(",")

        if options.install or options.upgrade:
            # These options require a distribution config file.
            # Open it up and parse it:
            try:
                dist_config_dict = configobj.ConfigObj(options.dist_config,
                                                       file_error=True,
                                                       encoding='utf-8')
            except IOError as e:
                sys.exit("Unable to open distribution configuration file: %s" % e)
            except SyntaxError as e:
                sys.exit("Syntax error in distribution configuration file '%s': %s"
                         % (options.dist_config, e))

        # The install command uses the distribution config file as its input.
        # Other commands use an existing config file.
        if options.install:
            config_dict = dist_config_dict
        else:
            try:
                config_path, config_dict = weecfg.read_config(options.config_path, args)
            except SyntaxError as e:
                sys.exit("Syntax error in configuration file: %s" % e)
            except IOError as e:
                sys.exit("Unable to open configuration file: %s" % e)
            self.logger.log("Using configuration file %s" % config_path)

        if options.upgrade:
            # Update the config dictionary, then merge it with the distribution
            # dictionary
            weecfg.update_and_merge(config_dict, dist_config_dict)

        elif options.install or options.reconfigure:
            # Extract stn_info from the config_dict and command-line options:
            stn_info = self.get_stn_info(config_dict, options)
            # Use it to modify the configuration file.
            weecfg.modify_config(config_dict, stn_info, self.logger, options.debug)

        elif options.list_skins:
            # print("we should print skins")
            # print(config_dict['StdReport']['SeasonsReport'])  
            weecfg.print_skins(config_dict)

            # don't want to save a backup weewx.conf needlessly
            sys.exit(0)

        elif options.enable_skin:
            print("enable skin '%s'" % options.enable_skin);
            enable_status = weecfg.get_enable_status(config_dict,options.enable_skin)
            if enable_status == 'invalid_skin_name':
                print("invalid skin name '%s' - run '--list-skins' for a list" % options.enable_skin)
                sys.exit(1)
            elif enable_status is True:
                print("skin '%s' is already enabled" % options.enable_skin)
            elif enable_status is False:
                print("skin '%s' is disabled - enabling" % options.enable_skin)
                # enable, saving old weewx.conf
            elif enable_status == 'undefined':
                print("skin '%s' enable status is undefined - enabling" % options.enable_skin)
            else:
                print("enable_skin unknown error for skin '%s'" % (options.enable_skin))
            sys.exit(0)

        elif options.disable_skin:
            print("disable skin '%s'" % options.disable_skin);
            enable_status = weecfg.get_enable_status(config_dict,options.disable_skin)
            if enable_status == 'invalid_skin_name':
                print("invalid skin name '%s' - run '--list-skins' for a list" % options.disable_skin)
                sys.exit(1)
            elif enable_status is True:
                print("skin '%s' is enabled - disabling" % options.disable_skin)
                # disable, saving old weewx.conf
            elif enable_status is False:
                print("skin '%s' is already disabled" % options.disable_skin)
            elif enable_status == 'undefined':
                print("skin '%s' enable status is undefined - enabling" % options.disable_skin)
            else:
                print("disable_skin unknown error for skin '%s'" % (options.enable_skin))
            sys.exit(0)

        elif options.disable_skin:
            print("disable skin '%s'" % options.disable_skin);
            # check skin exists
            # check it's not already disabled
            # disable if needed, saving old weewx.conf
            sys.exit(0)

        else:
            sys.exit("Internal logic error in config.py")

        # For the path to the final file, use whatever was specified by --output,
        # or the original path if that wasn't specified
        output_path = options.output or config_path

        # Save weewx.conf, backing up any old file.
        backup_path = weecfg.save(config_dict, output_path, not options.no_backup)
        if backup_path:
            self.logger.log("Saved backup to %s" % backup_path)

    def get_stn_info(self, config_dict, options):
        """Build the stn_info structure. Extract first from the config_dict object,
        then from any command-line overrides, then use defaults, then prompt the user
        for values."""

        # Start with values from the config file:
        stn_info = weecfg.get_station_info(config_dict)

        # Get command line overrides, and apply them to stn_info. If that leaves a value
        # unspecified, then get it from the defaults.
        for k in stn_info_defaults:
            # Override only if the option exists and is not None:
            if hasattr(options, k) and getattr(options, k) is not None:
                stn_info[k] = getattr(options, k)
            elif k not in stn_info:
                # Value is still not specified. Get a default value
                stn_info[k] = stn_info_defaults[k]

        # Unless --no-prompt has been specified, give the user a chance
        # to change things:
        if not options.no_prompt:
            prompt_info = weecfg.prompt_for_info(**stn_info)
            stn_info.update(prompt_info)
            driver = weecfg.prompt_for_driver(stn_info.get('driver'))
            stn_info['driver'] = driver
            stn_info.update(weecfg.prompt_for_driver_settings(driver, config_dict))

        return stn_info
