# Copyright (C) 2018 Red Hat, Inc., Jake Hunsaker <jhunsake@redhat.com>

# This file is part of the sos project: https://github.com/sosreport/sos
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# version 2 of the GNU General Public License.
#
# See the LICENSE file in the source distribution for further information.

from sos.plugins import Plugin, RedHatPlugin
from pipes import quote
from re import match


class Pulp(Plugin, RedHatPlugin):
    """Pulp platform"""

    plugin_name = "pulp"
    packages = ("pulp-server", "pulp-katello")
    option_list = [
        ('tasks', 'number of tasks to collect from DB queries', 'fast', 200)
    ]

    def setup(self):

        # get mongo DB host and port from line like:
        # seeds: host1:27017,host2:27017
        # take just the very first URI and ignore possible failover
        # if no such config is present, default to localhost:27017
        # further, take optional user credentials - here we assume the
        # credentials dont contain a whitespace character (that would
        # make the parsing more difficult)
        self.dbhost = "localhost"
        self.dbport = "27017"
        self.dbuser = ""
        self.dbpassword = ""
        try:
            for line in open("/etc/pulp/server.conf").read().splitlines():
                if match(r"^\s*seeds:\s+\S+:\S+", line):
                    uri = line.split()[1].split(',')[0].split(':')
                    self.dbhost = uri[0]
                    self.dbport = uri[1]
                if match(r"\s*username:\s+\S+", line):
                    self.dbuser = "-u %s" % line.split()[1]
                if match(r"\s*password:\s+\S+", line):
                    self.dbpassword = "-p %s" % line.split()[1]
        except IOError:
            # fallback when the cfg file is not accessible
            pass

        self.add_copy_spec([
            "/etc/pulp/*.conf",
            "/etc/pulp/server/plugins.conf.d/",
            "/etc/default/pulp*",
            "/var/log/httpd/pulp-http.log*",
            "/var/log/httpd/pulp-https.log*",
            "/var/log/httpd/pulp-http_access_ssl.log*",
            "/var/log/httpd/pulp-https_access_ssl.log*",
            "/var/log/httpd/pulp-http_error_ssl.log*",
            "/var/log/httpd/pulp-https_error_ssl.log*"
        ])

        num_tasks = self.get_option('tasks')

        mtasks = self.build_mongo_cmd(
            '\"DBQuery.shellBatchSize=%s;; '
            'db.task_status.find().sort({finish_time: -1})'
            '.pretty().shellPrint()\"' % num_tasks
        )

        mres = self.build_mongo_cmd(
            '\"DBQuery.shellBatchSize=%s;; '
            'db.reserved_resources.find().pretty().shellPrint()\"' % num_tasks
        )

        prun = self.build_mongo_cmd(
            r'"DBQuery.shellBatchSize=%s;; '
            r'db.task_status.find({state:{\$ne: \"finished\"}}).pretty()'
            r'.shellPrint()"' % num_tasks
        )

        # prints mongo collection sizes sorted from biggest and in human
        # readable output
        csizes = self.build_mongo_cmd(
            '\"function humanReadable(bytes) {'
            '  var i = -1;'
            '  var byteUnits = [\'kB\', \'MB\', \'GB\', \'TB\', \'PB\', '
            '                   \'EB\', \'ZB\', \'YB\'];'
            '  do {'
            '      bytes = bytes / 1024;'
            '      i++;'
            '  } while (bytes > 1024);'
            '  return Math.max(bytes, 0.1).toFixed(1) + \' \' + byteUnits[i];'
            '};'
            'var collectionNames = db.getCollectionNames(), stats = [];'
            'collectionNames.forEach(function (n) {'
            '                          stats.push(db[n].stats());'
            '                        });'
            'stats = stats.sort(function(a, b) {'
            '                     return b[\'size\'] - a[\'size\']; });'
            'for (var c in stats) {'
            '  print(stats[c][\'ns\'] + \': \' +'
            '        humanReadable(stats[c][\'size\']) + \' (\' +'
            '        humanReadable(stats[c][\'storageSize\']) + \')\'); }\"'
        )

        dbstats = self.build_mongo_cmd('\"db.stats()\"')

        self.add_cmd_output(mtasks, suggest_filename="mongo-task_status")
        self.add_cmd_output(mres, suggest_filename="mongo-reserved_resources")
        self.add_cmd_output(prun, suggest_filename="pulp-running_tasks")
        self.add_cmd_output(csizes, suggest_filename="mongo-collection_sizes")
        self.add_cmd_output(dbstats, suggest_filename="mongo-db_stats")

    def build_mongo_cmd(self, query):
        _cmd = "bash -c %s"
        _mondb = "--host %s --port %s %s %s" % (self.dbhost, self.dbport,
                                                self.dbuser, self.dbpassword)
        _moncmd = "mongo pulp_database %s --eval %s"
        return _cmd % quote(_moncmd % (_mondb, query))

    def postproc(self):
        etcreg = r"(([a-z].*(passw|token|cred|secret).*)\:(\s))(.*)"
        repl = r"\1 ********"
        self.do_path_regex_sub("/etc/pulp/(.*).conf", etcreg, repl)
        jreg = r"(\s*\".*(passw|cred|token|secret).*\:)(.*)"
        self.do_path_regex_sub("/etc/pulp(.*)(.json$)", jreg, repl)

# vim: set et ts=4 sw=4 :
