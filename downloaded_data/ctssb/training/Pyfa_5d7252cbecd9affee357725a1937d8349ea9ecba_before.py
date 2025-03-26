# remoteGuidanceDisruptFalloff
#
# Used by:
# Variations of module: Standup Weapon Disruptor
type = "active", "projected"

def handler(fit, module, context):
    if "projected" in context:
        for srcAttr, tgtAttr in (
            ("aoeCloudSizeBonus", "aoeCloudSize"),
            ("aoeVelocityBonus", "aoeVelocity"),
            ("missileVelocityBonus", "maxVelocity"),
            ("explosionDelayBonus", "explosionDelay"),
        ):
            fit.modules.filteredChargeBoost(lambda mod: mod.charge.requiresSkill("Missile Launcher Operation"),
                                        tgtAttr, src.getModifiedItemAttr(srcAttr),
                                        stackingPenalties=True, remoteResists=True)

        fit.modules.filteredItemBoost(lambda mod: mod.item.requiresSkill("Gunnery"),
                                      "trackingSpeed", module.getModifiedItemAttr("trackingSpeedBonus"),
                                      stackingPenalties = True, remoteResists=True)
        fit.modules.filteredItemBoost(lambda mod: mod.item.requiresSkill("Gunnery"),
                                      "maxRange", module.getModifiedItemAttr("maxRangeBonus"),
                                      stackingPenalties = True, remoteResists=True)
        fit.modules.filteredItemBoost(lambda mod: mod.item.requiresSkill("Gunnery"),
                                      "falloff", module.getModifiedItemAttr("falloffBonus"),
                                      stackingPenalties = True, remoteResists=True)

# TODO
# believe this doesn't actual require skills to use.
# Need to figure out how to remove the skill req *OR* tie it to the structure.