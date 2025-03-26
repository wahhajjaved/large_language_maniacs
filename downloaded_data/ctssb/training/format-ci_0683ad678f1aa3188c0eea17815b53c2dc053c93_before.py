#!/usr/bin/python3


from flask import render_template


def cook_projects_html(projects):
	return "".join(map(lambda pr: render_template("repo_box.html", repo_owner=pr[0], repo_name=pr[1], repo_passed=pr[2], repo_job_amount=pr[3],
	                                              last_job_id=eval(pr[4])[-1]), projects))

def cook_job_log(job):
	if job is not None:
		return "<pre>" + job[0] + "</pre>"
	else:
		return ""
