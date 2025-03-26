from lxml import etree
from collections import defaultdict

def getMapping(type='project'):
	m = defaultdict(str)

	if type == 'project':
		m['title'] = 'title'
		m['status'] = 'desc_status'
		m['objectives'] = 'objective'

		m['project_acronym'] = 'projectacronym'
		m['project_call'] = 'call_identifier'
		m['reference_number'] = 'projectreference'
		m['rcn'] = 'rcn'
		m['programme_acronym'] = 'programmeacronym'
		m['subprogramme_area'] = 'subprogrammearea'
		m['programme_type'] = 'programmetype'
		m['contract_type'] = 'contract_type'
		m['contract_type_desc'] = 'contract_type_desc'
		m['subject_index'] = 'subjectindex'
		m['subject_index_code'] = 'subjectindexcode'
		
		m['start_date'] = 'projectstartdate'
		m['end_date'] = 'projectenddate'
		m['duration'] = 'projectduration'
		m['cost'] = 'projectcost'
		m['funding'] = 'projectfunding'

		m['rec_qv_date'] = 'rec_qv_date'
		m['last_updated'] = 'last_update_date'
		m['publication_date'] = 'rec_publication_date'
		m['creation_date'] = 'rec_creation_date'
	
	elif type == 'organization':
		m['contact_full_name'] = 'contact'
		m['contact_first_name'] = 'contact_first_name'
		m['contact_last_name'] = 'contact_last_name'
		m['contact_title'] = 'contact_title'
		
		m['telephone'] = 'contact_tel'
		m['fax'] = 'contact_fax'

		m['id'] = 'org_id'
		m['name'] = 'legal_name'
		m['acronym'] = 'short_name'

		m['street'] = 'street_name'
		m['city'] = 'town'
		m['country'] = 'country_ccm'
		m['website'] = 'internet_homepage'
		m['order'] = 'participant_order'



	return m

def parse(rcn):
	# url = "http://cordis.europa.eu/projects/index.cfm?fuseaction=app.csa&action=read&rcn=" + str(rcn)
	
	url = '/Users/pvhee/code/parse_cordis/parse_cordis/tests/project.xml'
	# 
	# tree = etree.parse('/Users/pvhee/code/parse_cordis/parse_cordis/tests/project.xml')
	tree = etree.parse(url)

	# print(etree.tostring(doc, pretty_print=True))

	# print doc
	# print doc.find(/'hit')
	root = tree.getroot()

	p = defaultdict(str)

	hit = tree.find('responsedata').find('hit')
	# print hit.find('title').text
	




	# print participants

	for k,v in getMapping('project').iteritems():
		try:
			p[k] = hit.find(v).text
		except:
			continue


	p['participants'] = list()
	participants = root.xpath("//metadatagroup[@name='tag_erc_fields']/item")
	for participant in participants:
		p2 = defaultdict(str)
		for k,v in getMapping('organization').iteritems():
			try:
				p2[k] = participant.find(v).text
			except:
				continue

		if p2['order'] == "1":
			p['coordinator'] = p2['id']

		p['participants'].append(p2)

		# print participant[0].tag


	# m['']

	# p['title'] = hit.find('title').text
	# p['project_acronym'] = hit.find('projectacronym').text


	return p


