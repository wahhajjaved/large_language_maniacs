#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#   GHeimdall - A small web application for Google Apps SSO service.
#   Copyright (C) 2007 SIOS Technology, Inc.
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
#   USA.
#
#   $Id$

__author__ = 'tmatsuo@sios.com (Takashi MATSUO)'

from gheimdall import auth
import PAM

def pam_conv(auth, query_list):

  resp = []
    
  for i in range(len(query_list)):
    query, type = query_list[i]
    if type == PAM.PAM_PROMPT_ECHO_ON:
      data = auth.get_userdata()
      resp.append((data.get('password'), 0))
    elif type == PAM.PAM_PROMPT_ECHO_OFF:
      data = auth.get_userdata()
      resp.append((data.get('password'), 0))
    elif type == PAM.PAM_ERROR_MSG or type == PAM.PAM_TEXT_INFO:
      resp.append(('', 0));
    else:
      return None
  return resp

class PamAuthEngine(auth.BaseAuthEngine):

  def _prepare(self, config):
    # This is for standalone use.
    self.appname = config.get('apps.pam_appname')

  def _authenticate(self, user_name, password):
    pam = PAM.pam()
    pam.start(self.appname)
    pam.set_item(PAM.PAM_USER, user_name)
    pam.set_item(PAM.PAM_CONV, pam_conv)
    pam.set_userdata(dict(password=password))
    try:
      pam.authenticate()
      pam.acct_mgmt()
    except PAM.error, args:
      pam.close_session()
      raise auth.AuthException(args[0], args[1])
    except Exception, e:
      pam.close_session()
      raise auth.AuthException(e.__str__(), auth.ERR_UNKNOWN)
    else:
      pam.close_session()
      return True

cls = PamAuthEngine
