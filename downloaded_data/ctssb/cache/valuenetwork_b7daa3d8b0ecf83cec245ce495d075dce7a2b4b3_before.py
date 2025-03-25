from django import template

register = template.Library()

@register.filter
def reqs_related_agent(jn_reqs, agent):
    if jn_reqs and agent:
        reqs = []
        for req in jn_reqs:
            if req.project.agent == agent:
                reqs.append(req)
        return reqs
    else:
        return jn_reqs

@register.filter
def shares_related_project(shares, project):
    total = 0
    if shares and project:
        acc = project.shares_account_type()
        for sh in shares:
            if sh.resource_type == acc:
                total += sh.price_per_unit

            if hasattr(sh.resource_type, 'ocp_artwork_type'):
                if sh.resource_type.ocp_artwork_type == acc.ocp_artwork_type.rel_nonmaterial_type:
                    total += sh.quantity
        return int(total)
    return False
