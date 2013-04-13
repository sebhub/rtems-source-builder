#
# RTEMS Tools Project (http://www.rtems.org/)
# Copyright 2010-2013 Chris Johns (chrisj@rtems.org)
# All rights reserved.
#
# This file is part of the RTEMS Tools package in 'rtems-tools'.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

#
# Determine the defaults and load the specific file.
#

import glob
import pprint
import re
import os
import string

import error
import execute
import git
import macros
import path
import sys

basepath = 'sb'

class command_line:
    """Process the command line in a common way for all Tool Builder commands."""

    def __init__(self, argv, optargs, _defaults, command_path):
        self._long_opts = {
            # key                 macro              handler            param  defs    init
            '--prefix'         : ('_prefix',         self._lo_path,     True,  None,  False),
            '--topdir'         : ('_topdir',         self._lo_path,     True,  None,  False),
            '--configdir'      : ('_configdir',      self._lo_path,     True,  None,  False),
            '--builddir'       : ('_builddir',       self._lo_path,     True,  None,  False),
            '--sourcedir'      : ('_sourcedir',      self._lo_path,     True,  None,  False),
            '--tmppath'        : ('_tmppath',        self._lo_path,     True,  None,  False),
            '--jobs'           : ('_jobs',           self._lo_jobs,     True,  'max', True),
            '--log'            : ('_logfile',        self._lo_string,   True,  None,  False),
            '--url'            : ('_url_base',       self._lo_string,   True,  None,  False),
            '--targetcflags'   : ('_targetcflags',   self._lo_string,   True,  None,  False),
            '--targetcxxflags' : ('_targetcxxflags', self._lo_string,   True,  None,  False),
            '--libstdcxxflags' : ('_libstdcxxflags', self._lo_string,   True,  None,  False),
            '--force'          : ('_force',          self._lo_bool,     False, '0',   True),
            '--quiet'          : ('_quiet',          self._lo_bool,     False, '0',   True),
            '--trace'          : ('_trace',          self._lo_bool,     False, '0',   True),
            '--dry-run'        : ('_dry_run',        self._lo_bool,     False, '0',   True),
            '--warn-all'       : ('_warn_all',       self._lo_bool,     False, '0',   True),
            '--no-clean'       : ('_no_clean',       self._lo_bool,     False, '0',   True),
            '--keep-going'     : ('_keep_going',     self._lo_bool,     False, '0',   True),
            '--always-clean'   : ('_always_clean',   self._lo_bool,     False, '0',   True),
            '--host'           : ('_host',           self._lo_triplets, True,  None,  False),
            '--build'          : ('_build',          self._lo_triplets, True,  None,  False),
            '--target'         : ('_target',         self._lo_triplets, True,  None,  False),
            '--help'           : (None,              self._lo_help,     False, None,  False)
            }

        self.command_path = command_path
        self.command_name = path.basename(argv[0])
        self.argv = argv
        self.args = argv[1:]
        self.optargs = optargs
        self.defaults = _defaults
        self.opts = { 'params' : [] }
        for lo in self._long_opts:
            self.opts[lo[2:]] = self._long_opts[lo][3]
            if self._long_opts[lo][4]:
                self.defaults[self._long_opts[lo][0]] = ('none', 'none', self._long_opts[lo][3])

    def __str__(self):
        def _dict(dd):
            s = ''
            ddl = dd.keys()
            ddl.sort()
            for d in ddl:
                s += '  ' + d + ': ' + str(dd[d]) + '\n'
            return s

        s = 'command: ' + self.command() + \
            '\nargs: ' + str(self.args) + \
            '\nopts:\n' + _dict(self.opts)

        return s

    def _lo_string(self, opt, macro, value):
        if value is None:
            raise error.general('option requires a value: %s' % (opt))
        self.opts[opt[2:]] = value
        self.defaults[macro] = value

    def _lo_path(self, opt, macro, value):
        if value is None:
            raise error.general('option requires a path: %s' % (opt))
        value = path.shell(value)
        self.opts[opt[2:]] = value
        self.defaults[macro] = value

    def _lo_jobs(self, opt, macro, value):
        if value is None:
            raise error.general('option requires a value: %s' % (opt))
        ok = False
        if value in ['max', 'none', 'half']:
            ok = True
        else:
            try:
                i = int(value)
                ok = True
            except:
                pass
            if not ok:
                try:
                    f = float(value)
                    ok = True
                except:
                    pass
        if not ok:
            raise error.general('invalid jobs option: %s' % (value))
        self.defaults[macro] = value
        self.opts[opt[2:]] = value

    def _lo_bool(self, opt, macro, value):
        if value is not None:
            raise error.general('option does not take a value: %s' % (opt))
        self.opts[opt[2:]] = '1'
        self.defaults[macro] = '1'

    def _lo_triplets(self, opt, macro, value):
        #
        # This is a target triplet. Run it past config.sub to make make sure it
        # is ok.  The target triplet is 'cpu-vendor-os'.
        #
        e = execute.capture_execution()
        config_sub = path.join(self.command_path,
                               basepath, 'config.sub')
        exit_code, proc, output = e.shell(config_sub + ' ' + value)
        if exit_code == 0:
            value = output
        self.defaults[macro] = ('triplet', 'none', value)
        self.opts[opt[2:]] = value
        _cpu = macro + '_cpu'
        _arch = macro + '_arch'
        _vendor = macro + '_vendor'
        _os = macro + '_os'
        _arch_value = ''
        _vendor_value = ''
        _os_value = ''
        dash = value.find('-')
        if dash >= 0:
            _arch_value = value[:dash]
            value = value[dash + 1:]
        dash = value.find('-')
        if dash >= 0:
            _vendor_value = value[:dash]
            value = value[dash + 1:]
        if len(value):
            _os_value = value
        self.defaults[_cpu]    = _arch_value
        self.defaults[_arch]   = _arch_value
        self.defaults[_vendor] = _vendor_value
        self.defaults[_os]     = _os_value

    def _lo_help(self, opt, macro, value):
        self.help()

    def help(self):
        print '%s: [options] [args]' % (self.command_name)
        print 'RTEMS Source Builder, an RTEMS Tools Project (c) 2012-2013 Chris Johns'
        print 'Options and arguments:'
        print '--force                : Force the build to proceed'
        print '--quiet                : Quiet output (not used)'
        print '--trace                : Trace the execution'
        print '--dry-run              : Do everything but actually run the build'
        print '--warn-all             : Generate warnings'
        print '--no-clean             : Do not clean up the build tree'
        print '--always-clean         : Always clean the build tree, even with an error'
        print '--jobs                 : Run with specified number of jobs, default: num CPUs.'
        print '--host                 : Set the host triplet'
        print '--build                : Set the build triplet'
        print '--target               : Set the target triplet'
        print '--prefix path          : Tools build prefix, ie where they are installed'
        print '--topdir path          : Top of the build tree, default is $PWD'
        print '--configdir path       : Path to the configuration directory, default: ./config'
        print '--builddir path        : Path to the build directory, default: ./build'
        print '--sourcedir path       : Path to the source directory, default: ./source'
        print '--tmppath path         : Path to the temp directory, default: ./tmp'
        print '--log file             : Log file where all build out is written too'
        print '--url url              : URL to look for source'
        print '--targetcflags flags   : List of C flags for the target code'
        print '--targetcxxflags flags : List of C++ flags for the target code'
        print '--libstdcxxflags flags : List of C++ flags to build the target libstdc++ code'
        print '--with-<label>         : Add the --with-<label> to the build'
        print '--without-<label>      : Add the --without-<label> to the build'
        if self.optargs:
            for a in self.optargs:
                print '%-22s : %s' % (a, self.optargs[a])
        raise error.exit()

    def process(self):
        arg = 0
        while arg < len(self.args):
            a = self.args[arg]
            if a == '-?':
                self.help()
            elif a.startswith('--'):
                los = a.split('=')
                lo = los[0]
                if lo in self._long_opts:
                    long_opt = self._long_opts[lo]
                    if len(los) == 1:
                        if long_opt[2]:
                            if arg == len(args) - 1:
                                raise error.general('option requires a parameter: %s' % (lo))
                            arg += 1
                            value = args[arg]
                        else:
                            value = None
                    else:
                        value = '='.join(los[1:])
                    long_opt[1](lo, long_opt[0], value)
            else:
                self.opts['params'].append(a)
            arg += 1

    def post_process(self):
        if self.defaults['_host'] == self.defaults['nil']:
            raise error.general('host not set')
        if '_ncpus' not in self.defaults:
            raise error.general('host number of CPUs not set')
        ncpus = self.jobs(self.defaults['_ncpus'])
        if ncpus > 1:
            self.defaults['_smp_mflags'] = '-j %d' % (ncpus)
        else:
            self.defaults['_smp_mflags'] = self.defaults['nil']

    def command(self):
        return path.join(self.command_path, self.command_name)

    def force(self):
        return self.opts['force'] != '0'

    def dry_run(self):
        return self.opts['dry-run'] != '0'

    def set_dry_run(self):
        self.opts['dry-run'] = '1'

    def quiet(self):
        return self.opts['quiet'] != '0'

    def trace(self):
        return self.opts['trace'] != '0'

    def warn_all(self):
        return self.opts['warn-all'] != '0'

    def keep_going(self):
        return self.opts['keep-going'] != '0'

    def no_clean(self):
        return self.opts['no-clean'] != '0'

    def always_clean(self):
        return self.opts['always-clean'] != '0'

    def jobs(self, cpus):
        cpus = int(cpus)
        if self.opts['jobs'] == 'none':
            cpus = 0
        elif self.opts['jobs'] == 'max':
            pass
        elif self.opts['jobs'] == 'half':
            cpus = cpus / 2
        else:
            ok = False
            try:
                i = int(self.opts['jobs'])
                cpus = i
                ok = True
            except:
                pass
            if not ok:
                try:
                    f = float(self.opts['jobs'])
                    cpus = f * cpus
                    ok = True
                except:
                    pass
                if not ok:
                    raise error.internal('bad jobs option: %s' % (self.opts['jobs']))
        if cpus <= 0:
            cpu = 1
        return cpus

    def params(self):
        return self.opts['params']

    def get_arg(self, arg):
        if not arg in self.optargs:
            raise error.internal('bad arg: %s' % (arg))
        for a in self.args:
            sa = a.split('=')
            if sa[0].startswith(arg):
                return sa
        return None

    def get_config_files(self, config):
        #
        # Convert to shell paths and return shell paths.
        #
        # @fixme should this use a passed in set of defaults and not
        #        not the initial set of values ?
        #
        config = path.shell(config)
        if '*' in config or '?' in config:
            print config
            configdir = path.dirname(config)
            configbase = path.basename(config)
            if len(configbase) == 0:
                configbase = '*'
            if not configbase.endswith('.cfg'):
                configbase = configbase + '.cfg'
            if len(configdir) == 0:
                configdir = self.macros.expand(self.defaults['_configdir'])
            configs = []
            for cp in configdir.split(':'):
                hostconfigdir = path.host(cp)
                for f in glob.glob(os.path.join(hostconfigdir, configbase)):
                    configs += path.shell(f)
        else:
            configs = [config]
        return configs

    def config_files(self):
        configs = []
        for config in self.opts['params']:
            configs.extend(self.get_config_files(config))
        return configs

    def logfiles(self):
        if 'log' in self.opts and self.opts['log'] is not None:
            return self.opts['log'].split(',')
        return ['stdout']

    def urls(self):
        if self.opts['url'] is not None:
            return self.opts['url'].split(',')
        return None

def load(args, optargs = None, defaults = '%{_sbdir}/defaults.mc'):
    """
    Copy the defaults, get the host specific values and merge them overriding
    any matching defaults, then create an options object to handle the command
    line merging in any command line overrides. Finally post process the
    command line.
    """

    #
    # The path to this command.
    #
    command_path = path.dirname(args[0])
    if len(command_path) == 0:
        command_path = '.'

    #
    # The command line contains the base defaults object all build objects copy
    # and modify by loading a configuration.
    #
    o = command_line(args,
                     optargs,
                     macros.macros(name = defaults,
                                   sbdir = command_path),
                     command_path)

    overrides = None
    if os.name == 'nt':
        import windows
        overrides = windows.load()
    elif os.name == 'posix':
        uname = os.uname()
        try:
            if uname[0].startswith('CYGWIN_NT'):
                import windows
                overrides = windows.load()
            elif uname[0] == 'Darwin':
                import darwin
                overrides = darwin.load()
            elif uname[0] == 'FreeBSD':
                import freebsd
                overrides = freebsd.load()
            elif uname[0] == 'Linux':
                import linux
                overrides = linux.load()
        except:
            pass
    else:
        raise error.general('unsupported host type; please add')
    if overrides is None:
        raise error.general('no hosts defaults found; please add')
    for k in overrides:
        o.defaults[k] = overrides[k]

    o.process()
    o.post_process()

    repo = git.repo(o.defaults.expand('%{_sbdir}'), o)
    if repo.valid():
        repo_valid = '1'
        repo_head = repo.head()
        repo_clean = repo.clean()
        repo_id = repo_head
        if not repo_clean:
            repo_id += '-modified'
    else:
        repo_valid = '0'
        repo_head = '%{nil}'
        repo_clean = '%{nil}'
        repo_id = 'no-repo'
    o.defaults['_sbgit_valid'] = repo_valid
    o.defaults['_sbgit_head']  = repo_head
    o.defaults['_sbgit_clean'] = str(repo_clean)
    o.defaults['_sbgit_id']    = repo_id
    return o

def run(args):
    try:
        _opts = load(args = args)
        print 'Options:'
        print _opts
        print 'Defaults:'
        print _opts.defaults
    except error.general, gerr:
        print gerr
        sys.exit(1)
    except error.internal, ierr:
        print ierr
        sys.exit(1)
    except error.exit, eerr:
        pass
    except KeyboardInterrupt:
        _notice(opts, 'abort: user terminated')
        sys.exit(1)
    sys.exit(0)

if __name__ == '__main__':
    run(sys.argv)