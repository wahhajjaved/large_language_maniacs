# Copyright 2009 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Module for all nameserver health checks."""

__author__ = 'tstromberg@google.com (Thomas Stromberg)'

import random
import sys
import time

# See if a third_party library exists -- use it if so.
try:
  import third_party
except ImportError:
  pass

import dns.reversename

SANITY_CHECKS_URL='http://namebench.googlecode.com/svn/wiki/HostnameSanityChecks.wiki'
WILDCARD_DOMAINS = ('live.com.', 'blogspot.com.', 'wordpress.com.')
LIKELY_HIJACKS = ['www.google.com.', 'windowsupdate.microsoft.com.', 'www.paypal.com.']

# How many checks to consider when calculating ns check_duration
SHARED_CACHE_TIMEOUT_MULTIPLIER = 1.25
ROOT_SERVER_TIMEOUT_MULTIPLIER = 0.5
CENSORSHIP_TIMEOUT_MULTIPLIER = 2
MAX_STORE_ATTEMPTS = 4
TOTAL_WILDCARDS_TO_STORE = 2
MAX_PORT_BEHAVIOR_TRIES = 2

class NameServerHealthChecks(object):
  """Health checks for a nameserver."""

  def TestAnswers(self, record_type, record, expected, fatal=True, timeout=None):
    """Test to see that an answer returns correct IP's.

    Args:
      record_type: text record type for NS query (A, CNAME, etc)
      record: string to query for
      expected: tuple of strings expected in all answers

    Returns:
      (is_broken, error_msg, duration)
    """
    is_broken = False
    response_text = None
    unmatched_answers = []
    warning = None
    if not timeout:
      timeout = self.health_timeout
    (response, duration, error_msg) = self.TimedRequest(record_type, record, timeout)
    if not response:
      if not error_msg:
        error_msg = "No response"
      is_broken = True
    elif not response.answer:
      if fatal:
        is_broken = True
      # Avoid preferring broken DNS servers that respond quickly
      duration = self.health_timeout
      error_msg = 'No answer for %s' % record
    else:
      unmatched_answers = []
      found_usable_record = False

      for answer in response.answer:
        if found_usable_record:
          break

        # Process the first sane rdata object available in the answers
        for rdata in answer:
          # CNAME
          if rdata.rdtype == 5:
            reply = str(rdata.target)
          # A Record
          elif rdata.rdtype ==  1:
            reply = str(rdata.address)
          else:
            continue

          found_usable_record = True
          found_match = False
          for string in expected:
            if reply.startswith(string) or reply.endswith(string):
              found_match = True
              break
          if not found_match:
            unmatched_answers.append(reply)

      if unmatched_answers:
        hijack_text = ', '.join(unmatched_answers).rstrip('.')
        if record in LIKELY_HIJACKS:
          error_msg = '%s is hijacked: %s' % (record.rstrip('.'), hijack_text)
        else:
          error_msg = '%s appears incorrect: %s' % (record.rstrip('.'), hijack_text)

    return (is_broken, error_msg, duration)

  def TestBindVersion(self):
    """Test for BIND version. This acts as a pretty decent ping."""
    (response, duration, error_msg) = self.RequestVersion()
    return (False, error_msg, duration)
    
  def TestNodeId(self):
    """Test for BIND version. This acts as a pretty decent ping."""
    (response, duration, error_msg) = self.RequestNodeId()
    return (False, False, 0.0)
    
  def TestNegativeResponse(self, prefix=None):
    """Test for NXDOMAIN hijaaking."""
    is_broken = False
    warning = None
    if prefix:
      hostname = prefix
      warning_suffix = ' (%s)' % prefix
    else:
      hostname = 'test'
      warning_suffix = ''
    poison_test = '%s.nb%s.google.com.' % (hostname, random.random())
    (response, duration, error_msg) = self.TimedRequest('A', poison_test,
                                                  timeout=self.health_timeout*2)
    if not response:
      if not error_msg:
        error_msg = "No response"
      is_broken = True
    elif response.answer:
      error_msg = 'NXDOMAIN Hijacking' + warning_suffix

    return (is_broken, error_msg, duration)
  
  def TestWwwNegativeResponse(self):
    return self.TestNegativeResponse(prefix='www')

  def TestRootServerResponse(self):
    return self.TestAnswers('A', 'a.root-servers.net.', '198.41.0.4')
    
  def TestPortBehavior(self, tries=0):
    """This is designed to be called multiple times to retry bad results."""
    
    if self.port_behavior:
      if 'UNKNOWN' not in self.port_behavior:
        return (False, None, 0)

    tries += 1
    response = self.TimedRequest('TXT', 'porttest.dns-oarc.net.', timeout=5)[0]
    if response and response.answer:
      if len(response.answer) > 1:
        text = response.answer[1].to_rdataset().to_text()
        self.port_behavior = text.split('"')[1]

    if (not self.port_behavior or 'UNKNOWN' in self.port_behavior) and tries < MAX_PORT_BEHAVIOR_TRIES:
      time.sleep(1)
      return self.TestPortBehavior(tries=tries)
    
#    print "%s behavior: %s (tries=%s)" % (self, self.port_behavior, tries)
    return (False, None, 0)
    
  def StoreAnycastID(self):
    if not self.is_global:
      return (False, None, 0)

      (response, duration, error_msg) = self.TimedRequest('TXT', 'version.bind.',
                                                    timeout=self.ping_timeout,
                                                    rdataclass='CHAOS')
      return (error_msg, False, duration)
      

  def StoreWildcardCache(self):
    """Store a set of wildcard records."""
    timeout = self.health_timeout * SHARED_CACHE_TIMEOUT_MULTIPLIER
    attempted = []

    while len(self.cache_checks) != TOTAL_WILDCARDS_TO_STORE:
      if len(attempted) == MAX_STORE_ATTEMPTS:
        self.disabled = True
        self.AddFailure('Could not recursively query: %s' % ', '.join(attempted))
        return False
      domain = random.choice(WILDCARD_DOMAINS)
      hostname = 'namebench%s.%s' % (random.randint(1,2**32), domain)
      attempted.append(hostname)
      (response, duration, exc) = self.TimedRequest('A', hostname, timeout=timeout)
      if response and response.answer:
        self.cache_checks.append((hostname, response, self.timer()))
      else:
        sys.stdout.write('x')


  def TestSharedCache(self, other_ns):
    """Is this nameserver sharing a cache with another nameserver?

    Args:
      other_ns: A nameserver to compare it to.

    Returns:
      A tuple containing:
        - Boolean of whether or not this host has a shared cache
        - The faster NameServer object
        - The slower NameServer object
    """
    timeout = self.health_timeout * SHARED_CACHE_TIMEOUT_MULTIPLIER
    checked = []
    shared = False

    if self.disabled or other_ns.disabled:
      return False

    if not other_ns.cache_checks:
      print "%s has no cache checks (disabling - how did this happen?)" % other_ns
      other_ns.disabled = True
      return False

    for (ref_hostname, ref_response, ref_timestamp) in other_ns.cache_checks:
      (response, duration, error_msg) = self.TimedRequest('A', ref_hostname, timeout=timeout)
      # Retry once - this *may* cause false positives however, as the TTL may be updated.
      if not response or not response.answer:
        sys.stdout.write('x')
        (response, duration, error_msg) = self.TimedRequest('A', ref_hostname, timeout=timeout)
        
      if response and response.answer:
        ref_ttl = ref_response.answer[0].ttl
        ttl = response.answer[0].ttl
        delta = abs(ref_ttl - ttl)
        query_age = self.timer() - ref_timestamp
        delta_age_delta = abs(query_age - delta)

        if delta > 0 and delta_age_delta < 2:
          return other_ns
      else:
        sys.stdout.write('!')
      checked.append(ref_hostname)

    if not checked:
      self.AddFailure('Failed to test %s wildcard caches'  % len(other_ns.cache_checks))
    return shared

  def CheckCensorship(self, tests):
     """Check to see if results from a nameserver are being censored."""
     for (check, expected) in tests:
       (req_type, req_name) = check.split(' ')
       expected_values = expected.split(',')
       result = self.TestAnswers(req_type.upper(), req_name, expected_values,
                                 timeout=self.health_timeout * CENSORSHIP_TIMEOUT_MULTIPLIER)
       warning = result[1]
       if warning:
         self.warnings.add(warning)

  def CheckHealth(self, sanity_checks=None, fast_check=False, final_check=False, port_check=False):
    """Qualify a nameserver to see if it is any good."""

    if fast_check:
      tests = [(self.TestBindVersion, [])]
      sanity_checks = []
    elif final_check:
      tests = [(self.TestWwwNegativeResponse, []), (self.TestPortBehavior, []), (self.TestNodeId, [])]
    elif port_check:
      tests = [(self.TestPortBehavior, []), (self.TestNodeId, [])]
    else:
      tests = [(self.TestNegativeResponse, [])]

    if sanity_checks:
      for (check, expected_value) in sanity_checks:
        (req_type, req_name) = check.split(' ')
        expected_values = expected_value.split(',')
        tests.append((self.TestAnswers, [req_type.upper(), req_name, expected_values]))

    for test in tests:
      (function, args) = test
      (is_broken, warning, duration) = function(*args)
      if args:
        test_name = args[1]
      else:
        test_name = function.__name__

      self.checks.append((test_name, is_broken, warning, duration))
      if is_broken:
        self.AddFailure('%s: %s' % (test_name, warning))
      if warning:
        # Special case for NXDOMAIN de-duplication
        if not ('NXDOMAIN' in warning and 'NXDOMAIN Hijacking' in self.warnings):
          self.warnings.add(warning)
      if self.disabled:
        break

    return self.disabled

