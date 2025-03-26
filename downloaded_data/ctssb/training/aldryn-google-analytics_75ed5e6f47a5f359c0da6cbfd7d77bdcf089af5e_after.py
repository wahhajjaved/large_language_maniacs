# -*- coding: utf-8 -*-
from cmscloud.template_api import registry
from django.conf import settings

GOOGLE_ANALYTICS_SCRIPT = """<script type="text/javascript">
  var _gaq = _gaq || [];
  _gaq.push(['_setAccount', '%(google_analytics_id)s']);
  _gaq.push(['_trackPageview']);
  (function() {
    var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
    ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
  })();
</script>"""


UNIVERSAL_ANALYTICS_SCRIPT = """<script>
  (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
  (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
  m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
  })(window,document,'script','//www.google-analytics.com/analytics.js','ga');

  ga('create', '%(google_analytics_id)s', 'auto');%(ga_individual)s
  ga('send', 'pageview');

</script>"""


def get_google_analytics_script(request):
    google_analytics_id = getattr(settings, 'GOOGLE_ANALYTICS_ID', None)
    use_universal_analytics = getattr(settings, 'GOOGLE_ANALYTICS_USE_UNIVERSAL', False)
    track_individuals = getattr(settings, 'GOOGLE_ANALYTICS_TRACK_INDIVIDUALS', False)
    if not google_analytics_id:
        return ''
    context = {
        'google_analytics_id': google_analytics_id,
        'ga_individual': '',
    }
    if track_individuals and not request.user.is_anonymous():
        context['ga_individual'] = """\n  ga('set', '&uid', %s);""" % request.user.id
    if use_universal_analytics:
        template = UNIVERSAL_ANALYTICS_SCRIPT
    else:
        template = GOOGLE_ANALYTICS_SCRIPT
    return template % context

registry.add_to_tail(get_google_analytics_script)
