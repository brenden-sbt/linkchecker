# -*- coding: iso-8859-1 -*-
# Copyright (C) 2000-2005  Bastian Kleineidam
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
"""
Main functions for link checking.
"""

import time
import sys
import os
import cgi
import socket
import select
import re
import urlparse
import urllib
import nntplib
import ftplib

import linkcheck.httplib2
import linkcheck.dns.exception


# we catch these exceptions, all other exceptions are internal
# or system errors
ExcList = [
    IOError,
    OSError, # OSError is thrown on Windows when a file is not found
    ValueError, # from httplib.py
    linkcheck.LinkCheckerError,
    linkcheck.dns.exception.DNSException,
    socket.timeout,
    socket.error,
    select.error,
    # nttp errors (including EOFError)
    nntplib.error_reply,
    nntplib.error_temp,
    nntplib.error_perm,
    nntplib.error_proto,
    EOFError,
    # http error
    linkcheck.httplib2.error,
    # ftp errors
    ftplib.error_reply,
    ftplib.error_temp,
    ftplib.error_perm,
    ftplib.error_proto,
]

ignored_schemes = r"""^(
acap        # application configuration access protocol
|afs        # Andrew File System global file names
|cid        # content identifier
|data       # data
|dav        # dav
|fax        # fax
|imap       # internet message access protocol
|ldap       # Lightweight Directory Access Protocol
|mailserver # Access to data available from mail servers
|mid        # message identifier
|mms        # multimedia stream
|modem      # modem
|nfs        # network file system protocol
|opaquelocktoken # opaquelocktoken
|pop        # Post Office Protocol v3
|prospero   # Prospero Directory Service
|rsync      # rsync protocol
|rtsp       # real time streaming protocol
|rtspu      # real time streaming protocol
|service    # service location
|shttp      # secure HTTP
|sip        # session initiation protocol
|tel        # telephone
|tip        # Transaction Internet Protocol
|tn3270     # Interactive 3270 emulation sessions
|vemmi      # versatile multimedia interface
|wais       # Wide Area Information Servers
|z39\.50r   # Z39.50 Retrieval
|z39\.50s   # Z39.50 Session
|chrome     # Mozilla specific
|find       # Mozilla specific
|clsid      # Microsoft specific
|javascript # JavaScript
|isbn       # ISBN (int. book numbers)
):"""

ignored_schemes_re = re.compile(ignored_schemes, re.VERBOSE)


def check_urls (consumer):
    """
    Main check function; checks all configured URLs until interrupted
    with Ctrl-C. If you call this function more than once, you can specify
    different configurations with the consumer parameter.

    @param consumer: an object where all runtime-dependent options are
        stored
    @type consumer: linkcheck.consumer.Consumer
    @return: None
    """
    try:
        _check_urls(consumer)
    except KeyboardInterrupt:
        consumer.abort()


def _check_urls (consumer):
    """
    Checks all configured URLs. Prints status information, calls logger
    methods.

    @param consumer: an object where all runtime-dependent options are
        stored
    @type consumer: linkcheck.consumer.Consumer
    @return: None
    """
    start_time = time.time()
    status_time = start_time
    while not consumer.finished():
        consumer.check_url()
        if consumer.config['status']:
            curtime = time.time()
            if (curtime - status_time) > 5:
                consumer.print_status(curtime, start_time)
                status_time = curtime
    consumer.logger_end_output()


# file extensions we can parse recursively
extensions = {
    "html": re.compile(r'(?i)\.s?html?$'),
    "opera": re.compile(r'^(?i)opera.adr$'), # opera bookmark file
    "css": re.compile(r'(?i)\.css$'), # CSS stylesheet
}


import linkcheck.checker.fileurl
import linkcheck.checker.ignoredurl
import linkcheck.checker.ftpurl
import linkcheck.checker.gopherurl
import linkcheck.checker.httpurl
import linkcheck.checker.httpsurl
import linkcheck.checker.mailtourl
import linkcheck.checker.telneturl
import linkcheck.checker.nntpurl
import linkcheck.checker.errorurl


def set_intern_url (url, klass, config):
    """
    Add intern url pattern for url given on the command line.

    @param url: URL to add
    @type url: string
    @param klass: URL class
    @type klass: class object
    @param config: configuration data
    @type config: linkcheck.configuration.Configuration
    """
    linkcheck.log.debug(linkcheck.LOG_CHECK, "Set intern url for %r", url)
    if klass == linkcheck.checker.fileurl.FileUrl:
        linkcheck.log.debug(linkcheck.LOG_CHECK, "Add intern pattern ^file:")
        config['internlinks'].append(linkcheck.get_link_pat("^file:"))
    elif klass in [linkcheck.checker.httpurl.HttpUrl,
                   linkcheck.checker.httpsurl.HttpsUrl,
                   linkcheck.checker.ftpurl.FtpUrl]:
        domain = linkcheck.url.url_unicode_split(url)[1]
        domain, is_idn = linkcheck.url.idna_encode(domain)
        if domain:
            domain = "://%s" % re.escape(domain)
            linkcheck.log.debug(linkcheck.LOG_CHECK, "Add intern domain %r",
                                domain)
            # add scheme colon to link pattern
            config['internlinks'].append(linkcheck.get_link_pat(domain))


def absolute_url (base_url, base_ref, parent_url):
    """
    Search for the absolute url to detect the link type. This does not
    join any url fragments together! Returns the url in lower case to
    simplify urltype matching.

    @param base_url: base url from a link tag
    @type base_url: string or None
    @param base_ref: base url from <base> tag
    @type base_ref: string or None
    @param parent_url: url of parent document
    @type parent_url: string or None
    """
    if base_url and linkcheck.url.url_is_absolute(base_url):
        return base_url.lower()
    elif base_ref and linkcheck.url.url_is_absolute(base_ref):
        return base_ref.lower()
    elif parent_url and linkcheck.url.url_is_absolute(parent_url):
        return parent_url.lower()
    return u""


def get_url_from (base_url, recursion_level, consumer,
                  parent_url=None, base_ref=None, line=0, column=0,
                  name=u"", cmdline=None):
    """
    Get url data from given base data.

    @param base_url: base url from a link tag
    @type base_url: string
    @param recursion_level: current recursion level
    @type recursion_level: number
    @param consumer: consumer object
    @type consumer: linkcheck.checker.consumer.Consumer
    @param parent_url: parent url
    @type parent_url: string or None
    @param base_ref: base url from <base> tag
    @type base_ref string or None
    @param line: line number
    @type line: number
    @param column: column number
    @type column: number
    @param name: link name
    @type name: string
    @param cmdline: flag if url was given on command line
    @type cmdline: bool
    """
    default_encoding = "iso8859-15"
    if not isinstance(base_url, unicode):
        base_url = unicode(base_url, default_encoding, "ignore")
    if parent_url is not None and not isinstance(parent_url, unicode):
        parent_url = unicode(parent_url, default_encoding, "ignore")
    if base_ref is not None and not isinstance(base_ref, unicode):
        base_ref = unicode(base_ref, default_encoding, "ignore")
    if not isinstance(name, unicode):
        name = unicode(name, default_encoding, "ignore")
    #if cmdline and linkcheck.url.url_needs_quoting(base_url):
    #    base_url = linkcheck.url.url_quote(base_url)
    url = absolute_url(base_url, base_ref, parent_url)
    # test scheme
    if url.startswith("http:"):
        klass = linkcheck.checker.httpurl.HttpUrl
    elif url.startswith("ftp:"):
        klass = linkcheck.checker.ftpurl.FtpUrl
    elif url.startswith("file:"):
        klass = linkcheck.checker.fileurl.FileUrl
    elif url.startswith("telnet:"):
        klass = linkcheck.checker.telneturl.TelnetUrl
    elif url.startswith("mailto:"):
        klass = linkcheck.checker.mailtourl.MailtoUrl
    elif url.startswith("gopher:"):
        klass = linkcheck.checker.gopherurl.GopherUrl
    elif url.startswith("https:"):
        klass = linkcheck.checker.httpsurl.HttpsUrl
    elif url.startswith("nntp:") or \
         url.startswith("news:") or \
         url.startswith("snews:"):
        klass = linkcheck.checker.nntpurl.NntpUrl
    elif ignored_schemes_re.search(url):
        # ignored url
        klass = linkcheck.checker.ignoredurl.IgnoredUrl
    elif cmdline:
        # assume local file on command line
        klass = linkcheck.checker.fileurl.FileUrl
    else:
        # error url, no further checking, just log this
        klass = linkcheck.checker.errorurl.ErrorUrl
    if cmdline and not (consumer.config['internlinks'] or
                        consumer.config['externlinks']):
        # set automatic intern/extern stuff if no filter was given
        set_intern_url(url, klass, consumer.config)
    return klass(base_url, recursion_level, consumer,
                 parent_url=parent_url, base_ref=base_ref,
                 line=line, column=column, name=name)


def get_index_html (urls):
    """
    Construct artificial index.html from given URLs.

    @param urls: list with url strings
    @type urls: list of string
    """
    lines = ["<html>", "<body>"]
    for entry in urls:
        name = cgi.escape(entry)
        url = cgi.escape(urllib.quote(entry))
        lines.append('<a href="%s">%s</a>' % (url, name))
    lines.extend(["</body>", "</html>"])
    return os.linesep.join(lines)

