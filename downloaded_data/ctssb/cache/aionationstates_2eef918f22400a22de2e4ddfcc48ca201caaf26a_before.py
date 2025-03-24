import xml.etree.ElementTree as ET
import datetime

import pytest

import aionationstates


async def _inject_into_apiquery(self, text):
    assert len(self.results) == 1
    return await self.results[0](self.session, ET.fromstring(text))

aionationstates.session.ApiQuery.inject = _inject_into_apiquery


@pytest.fixture
def nation():
    return aionationstates.Nation('testlandia')


# Tests:


@pytest.mark.asyncio
async def test_name(nation):
    name = await nation.name().inject('''
    <NATION id="testlandia">
        <NAME>Testlandia</NAME>
    </NATION>
    ''')
    assert name == 'Testlandia'


# TODO finish with the basic stuff?


@pytest.mark.asyncio
async def test_motto(nation):
    motto = await nation.motto().inject('''
    <NATION id="testlandia">
        <MOTTO>Grr. Arg.</MOTTO>
    </NATION>
    ''')
    assert motto == 'Grr. Arg.'


@pytest.mark.asyncio
async def test_motto_mojibake(nation):
    motto = await nation.motto().inject('''
    <NATION id="testlandia">
        <MOTTO>&#x87;&#x87;&#x87;&#x87;&#x87;&#x87;&#x87;&#x87;&#x87;</MOTTO>
    </NATION>
    ''')
    assert motto == '‡‡‡‡‡‡‡‡‡'


@pytest.mark.asyncio
async def test_region(nation):
    region = await nation.region().inject('''
    <NATION id="testlandia">
        <REGION>Testregionia</REGION>
    </NATION>
    ''')
    assert region == aionationstates.Region('testregionia')


@pytest.mark.asyncio
async def test_founded(nation):
    founded = await nation.founded().inject('''
    <NATION id="testlandia">
        <FOUNDEDTIME>1496404379</FOUNDEDTIME>
    </NATION>
    ''')
    assert founded == datetime.datetime(2017, 6, 2, 11, 52, 59)


@pytest.mark.asyncio
async def test_wa_true(nation):
    wa = await nation.wa().inject('''
    <NATION id="testlandia">
        <UNSTATUS>WA Member</UNSTATUS>
    </NATION>
    ''')
    assert wa


@pytest.mark.asyncio
async def test_wa_false(nation):
    wa = await nation.wa().inject('''
    <NATION id="testlandia">
        <UNSTATUS>Non-member</UNSTATUS>
    </NATION>
    ''')
    assert not wa


@pytest.mark.asyncio
async def test_wa_delegate(nation):
    wa = await nation.wa().inject('''
    <NATION id="testlandia">
        <UNSTATUS>WA Delegate</UNSTATUS>
    </NATION>
    ''')
    assert wa


@pytest.mark.asyncio
async def test_freedom(nation):
    freedom = await nation.freedom().inject('''
    <NATION id="testlandia">
        <FREEDOM>
            <CIVILRIGHTS>Very Good</CIVILRIGHTS>
            <ECONOMY>Strong</ECONOMY>
            <POLITICALFREEDOM>Good</POLITICALFREEDOM>
        </FREEDOM>
    </NATION>
    ''')
    assert list(freedom.keys()) == ['Civil Rights',
                                    'Economy',
                                    'Political Freedom']
    assert freedom['Civil Rights'] == 'Very Good'
    assert freedom['Economy'] == 'Strong'
    assert freedom['Political Freedom'] == 'Good'


@pytest.mark.asyncio
async def test_freedomscores(nation):
    freedom = await nation.freedomscores().inject('''
    <NATION id="testlandia">
        <FREEDOMSCORES>
            <CIVILRIGHTS>11</CIVILRIGHTS>
            <ECONOMY>22</ECONOMY>
            <POLITICALFREEDOM>33</POLITICALFREEDOM>
        </FREEDOMSCORES>
    </NATION>
    ''')
    assert list(freedom.keys()) == ['Civil Rights',
                                    'Economy',
                                    'Political Freedom']
    assert freedom['Civil Rights'] == 11
    assert freedom['Economy'] == 22
    assert freedom['Political Freedom'] == 33


@pytest.mark.asyncio
async def test_govt(nation):
    govt = await nation.govt().inject('''
    <NATION id="testlandia">
        <GOVT>
            <ADMINISTRATION>5.6</ADMINISTRATION>
            <DEFENCE>13.4</DEFENCE>
            <EDUCATION>11.2</EDUCATION>
            <ENVIRONMENT>14.2</ENVIRONMENT>
            <HEALTHCARE>12.5</HEALTHCARE>
            <COMMERCE>6.1</COMMERCE>
            <INTERNATIONALAID>5.1</INTERNATIONALAID>
            <LAWANDORDER>8.2</LAWANDORDER>
            <PUBLICTRANSPORT>7.4</PUBLICTRANSPORT>
            <SOCIALEQUALITY>4.9</SOCIALEQUALITY>
            <SPIRITUALITY>5.1</SPIRITUALITY>
            <WELFARE>6.3</WELFARE>
        </GOVT>
    </NATION>
    ''')
    assert list(govt.keys()) == [
        'Administration', 'Defense', 'Education', 'Environment',
        'Healthcare', 'Industry', 'International Aid', 'Law & Order',
        'Public Transport', 'Social Policy', 'Spirituality', 'Welfare'
    ]
    assert govt['Administration'] == 5.6
    assert govt['Defense'] == 13.4
    assert govt['Education'] == 11.2
    assert govt['Environment'] == 14.2
    assert govt['Healthcare'] == 12.5
    assert govt['Industry'] == 6.1
    assert govt['International Aid'] == 5.1
    assert govt['Law & Order'] == 8.2
    assert govt['Public Transport'] == 7.4
    assert govt['Social Policy'] == 4.9
    assert govt['Spirituality'] == 5.1
    assert govt['Welfare'] == 6.3


@pytest.mark.asyncio
async def test_sectors(nation):
    sectors = await nation.sectors().inject('''
    <NATION id="testlandia">
        <SECTORS>
            <BLACKMARKET>0.14</BLACKMARKET>
            <GOVERNMENT>92.02</GOVERNMENT>
            <INDUSTRY>7.45</INDUSTRY>
            <PUBLIC>0.39</PUBLIC>
        </SECTORS>
    </NATION>
    ''')
    assert list(sectors.keys()) == [
        'Black Market (estimated)', 'Government', 'Private Industry',
        'State-Owned Industry'
    ]
    assert sectors['Black Market (estimated)'] == 0.14
    assert sectors['Government'] == 92.02
    assert sectors['Private Industry'] == 7.45
    assert sectors['State-Owned Industry'] == 0.39


@pytest.mark.asyncio
async def test_deaths(nation):
    deaths = await nation.deaths().inject('''
    <NATION id="testlandia">
        <DEATHS>
            <CAUSE type="Lost in Wilderness">6.7</CAUSE>
            <CAUSE type="Old Age">92.6</CAUSE>
            <CAUSE type="Acts of God">0.5</CAUSE>
            <CAUSE type="Suicide While in Police Custody">0.1</CAUSE>
        </DEATHS>
    </NATION>
    ''')
    assert deaths['Lost in Wilderness'] == 6.7
    assert deaths['Old Age'] == 92.6
    assert deaths['Acts of God'] == 0.5
    assert deaths['Suicide While in Police Custody'] == 0.1


@pytest.mark.asyncio
async def test_endorsements(nation):
    endorsements = await nation.endorsements().inject('''
    <NATION id="testlandia">
        <ENDORSEMENTS>abcd,efgh,jklm</ENDORSEMENTS>
    </NATION>
    ''')
    assert endorsements == [
        aionationstates.Nation('abcd'), aionationstates.Nation('efgh'),
        aionationstates.Nation('jklm')
    ]


@pytest.mark.asyncio
async def test_endorsements_none(nation):
    endorsements = await nation.endorsements().inject('''
    <NATION id="testlandia">
        <ENDORSEMENTS></ENDORSEMENTS>
    </NATION>
    ''')
    assert endorsements == []


@pytest.mark.asyncio
async def test_legislation(nation):
    legislation = await nation.legislation().inject('''
    <NATION id="testlandia">
        <LEGISLATION>
            <LAW><![CDATA[qwerty]]></LAW>
            <LAW><![CDATA[asdfg]]></LAW>
            <LAW><![CDATA[zxcvb]]></LAW>
            <LAW><![CDATA[ytrewq]]></LAW>
        </LEGISLATION>
    </NATION>
    ''')
    assert legislation == ['qwerty', 'asdfg', 'zxcvb', 'ytrewq']


@pytest.mark.asyncio
async def test_legislation_html(nation):
    legislation = await nation.legislation().inject('''
    <NATION id="testlandia">
        <LEGISLATION>
            <LAW><![CDATA[q <i>we</i> rty]]></LAW>
            <LAW><![CDATA[asd &amp; fg]]></LAW>
        </LEGISLATION>
    </NATION>
    ''')
    assert legislation == ['q <i>we</i> rty', 'asd &amp; fg']


@pytest.mark.asyncio
async def test_banners(nation):
    banners = await nation.banners().inject('''
    <NATION id="testlandia">
    <BANNERS>
        <BANNER>v1</BANNER>
        <BANNER>o4</BANNER>
        <BANNER>m2</BANNER>
    </BANNERS>
    </NATION>
    ''')
    assert banners[0] == 'https://www.nationstates.net/images/banners/v1.jpg'
    assert banners[1] == 'https://www.nationstates.net/images/banners/o4.jpg'
    assert banners[1] == 'https://www.nationstates.net/images/banners/m2.jpg'
