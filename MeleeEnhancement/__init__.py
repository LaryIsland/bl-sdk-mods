assert __import__("mods_base").__version_info__ >= (1, 12), "Please update the SDK"
assert __import__("unrealsdk").__version_info__ >= (3, 2, 0), "Please update the SDK"

from copy import copy
from typing import Any

import unrealsdk
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from mods_base import CoopSupport, build_mod, hook

BUZZAXE_BEHAVIORS_PATH: str = "GD_Lilac_SkillsBase.Buzzaxe.Projectile_Buzzaxe:BehaviorProviderDefinition_0"


@hook("WillowGame.PlayerSkillTree:Initialize")
def InjectSkillChanges(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    className = obj.Outer.PlayerClass.CharacterNameId.CharacterClassId.ClassName
    if className == "Assassin":
        Fearless_SkillDefinition = unrealsdk.find_object("SkillDefinition", "GD_Assassin_Skills.Cunning.Fearless")
        ShieldDelayAttribute = unrealsdk.find_object(
            "ResourcePoolAttributeDefinition",
            "D_Attributes.ShieldResourcePool.ShieldOnIdleRegenerationDelay"
        )

        # The skill tree is initialised again on every map load, so each change is only added once
        if not any(Effect.AttributeToModify == ShieldDelayAttribute
                   for Effect in Fearless_SkillDefinition.SkillEffectDefinitions):
            Fearless_SkillDefinition.SkillEffectDefinitions.append(
                unrealsdk.make_struct(
                    "SkillEffectData",
                    AttributeToModify=ShieldDelayAttribute,
                    EffectTarget=1,
                    ModifierType=2,
                    BaseModifierValue=unrealsdk.make_struct(
                        "AttributeInitializationData",
                        BaseValueConstant=1.0,
                        BaseValueAttribute=None,
                        InitializationDefinition=None,
                        BaseValueScaleConstant=1.0
                    ),
                    GradeToStartApplyingEffect=1,
                    PerGradeUpgradeInterval=1,
                    PerGradeUpgrade=unrealsdk.make_struct(
                        "AttributeInitializationData",
                        BaseValueConstant=1.0,
                        BaseValueAttribute=None,
                        InitializationDefinition=None,
                        BaseValueScaleConstant=1.0
                    )
                )
            )

        FearlessExtraDescription = (" Additionally, increases the delay before your shields "
                                    + "[skill]start to recharge[-skill] after being depleted.")
        if not Fearless_SkillDefinition.SkillDescription.endswith(FearlessExtraDescription):
            Fearless_SkillDefinition.SkillDescription += FearlessExtraDescription

        if not any(Presentation.Attribute == ShieldDelayAttribute
                   for Presentation in Fearless_SkillDefinition.SkillEffectPresentations):
            ShieldDelayPresentation = unrealsdk.construct_object(
                cls="AttributePresentationDefinition",
                outer=Fearless_SkillDefinition,
                name="AttributePresentationDefinition_ShieldDelay",
                flags=1,
                template_obj=unrealsdk.find_object(
                    "AttributePresentationDefinition",
                    "GD_Assassin_Skills.Cunning.Fearless:AttributePresentationDefinition_6"
                )
            )
            ShieldDelayPresentation.Attribute = ShieldDelayAttribute
            ShieldDelayPresentation.Description = "Shield Recharge Delay: $NUMBER$ sec."
            ShieldDelayPresentation.bDisplayAsPercentage = False
            ShieldDelayPresentation.bIncludeSuffixInTranslation = False
            ShieldDelayPresentation.bIncludePrefixInTranslation = False
            ShieldDelayPresentation.BasePriority = 1.0
            Fearless_SkillDefinition.SkillEffectPresentations.append(ShieldDelayPresentation)

        unrealsdk.find_object(
            "Behavior_SpawnProjectile",
            "GD_Assassin_Skills.ActionSkill.Skill_Stealth:BehaviorProviderDefinition_0.Behavior_SpawnProjectile_0"
        ).bInflictRadiusDamageOnOwner = False

    elif className == "Psycho":
        SilenceTheVoices_SkillDefinition = unrealsdk.find_object(
            "SkillDefinition",
            "GD_Lilac_Skills_Mania.Skills.SilenceTheVoices"
        )

        if not SilenceTheVoices_SkillDefinition.SkillEffectPresentations[1].bDisplayPercentAsFloat:
            SelfHitPresentation = unrealsdk.construct_object(
                cls="AttributePresentationDefinition",
                outer=SilenceTheVoices_SkillDefinition,
                name="AttributePresentationDefinition_2",
                flags=1,
                template_obj=SilenceTheVoices_SkillDefinition.SkillEffectPresentations[1]
            )
            SelfHitPresentation.bDisplayPercentAsFloat = True
            SelfHitPresentation.RoundingMode = 0

            SilenceTheVoices_SkillDefinition.SkillEffectPresentations[1] = SelfHitPresentation

        SilenceTheVoices_SkillDefinition.SkillEffectDefinitions[0].PerGradeUpgrade.BaseValueConstant = -0.013333333
        SilenceTheVoices_SkillDefinition.SkillEffectDefinitions[0].PerGradeUpgradeInterval = 1

        BuzzaxeBehaviors = unrealsdk.find_object("BehaviorProviderDefinition", BUZZAXE_BEHAVIORS_PATH)
        DynamiteSequence = next(Sequence for Sequence in BuzzaxeBehaviors.BehaviorSequences
                                if Sequence.BehaviorSequenceName == "Dynamite")

        # A second, damageless slag explosion goes off, which SlagExplosionIgnoresKrieg keeps off Krieg
        if not any(Data.Behavior.Name == "Behavior_Explode_Slag" for Data in DynamiteSequence.BehaviorData2):
            SlagExplosion = unrealsdk.construct_object(
                cls="Behavior_Explode",
                outer=BuzzaxeBehaviors,
                name="Behavior_Explode_Slag",
                flags=1,
                template_obj=unrealsdk.find_object("Behavior_Explode", f"{BUZZAXE_BEHAVIORS_PATH}.Behavior_Explode_6")
            )
            SlagExplosion.Definition = unrealsdk.find_object(
                "ExplosionDefinition", "GD_Explosions.Slag.Explosion_SlagMaster"
            )
            SlagExplosion.DamageFormula.BaseValueConstant = 0
            SlagExplosion.DamageFormula.BaseValueAttribute = None
            SlagExplosion.MomentumFormula.BaseValueConstant = 0
            SlagExplosion.StatusEffectChance.BaseValueConstant = 2.0

            SlagExplosionData = copy(DynamiteSequence.BehaviorData2[0])
            SlagExplosionData.Behavior = SlagExplosion
            SlagExplosionData.LinkedVariables.ArrayIndexAndLength = 0
            SlagExplosionData.OutputLinks.ArrayIndexAndLength = 0
            DynamiteSequence.BehaviorData2.append(SlagExplosionData)

            OnExplode = next(Event for Event in DynamiteSequence.EventData2 if Event.UserData.EventName == "OnExplode")
            OutputLinks = DynamiteSequence.ConsolidatedOutputLinkData
            LinksStart = OnExplode.OutputLinks.ArrayIndexAndLength >> 16
            LinksCount = OnExplode.OutputLinks.ArrayIndexAndLength & 0xFFFF
            NewLinksStart = len(OutputLinks)
            for Index in range(LinksStart, LinksStart + LinksCount):
                OutputLinks.append(copy(OutputLinks[Index]))
            SlagExplosionLink = copy(OutputLinks[LinksStart])
            # The link ID is in the top byte, events always use 0, then the behaviour's index
            SlagExplosionLink.LinkIdAndLinkedBehavior = len(DynamiteSequence.BehaviorData2) - 1
            SlagExplosionLink.ActivateDelay = 0
            OutputLinks.append(SlagExplosionLink)
            OnExplode.OutputLinks.ArrayIndexAndLength = (NewLinksStart << 16) | (LinksCount + 1)

        BuzzAxeBombadier_SkillDefinition = unrealsdk.find_object(
            "SkillDefinition",
            "GD_Lilac_Skills_Bloodlust.Skills.BuzzAxeBombadier"
        )
        BuzzAxeBombadierExtraDescription = " and [skill]slags[-skill] nearby enemies."
        if not BuzzAxeBombadier_SkillDefinition.SkillDescription.endswith(BuzzAxeBombadierExtraDescription):
            BuzzAxeBombadier_SkillDefinition.SkillDescription = (
                BuzzAxeBombadier_SkillDefinition.SkillDescription[:-1] + BuzzAxeBombadierExtraDescription
            )


@hook("WillowGame.WillowProjectile:Behavior_CauseRadiusDamage")
def SlagExplosionIgnoresKrieg(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    DamageCauser = args.DamageCauser
    if DamageCauser is not None and DamageCauser.Outer is not None \
            and DamageCauser.Outer._path_name() == BUZZAXE_BEHAVIORS_PATH:
        obj.bCauseRadiusDamageToInstigator = DamageCauser.Name != "Behavior_Explode_Slag"


mod = build_mod(
    coop_support=CoopSupport.RequiresAllPlayers,
    hooks=[InjectSkillChanges, SlagExplosionIgnoresKrieg]
)
mod.description = (
    "<font size='26' color='#de5b00'>       Melee Enhancement</font>\n\n"
    "\t\t\t<font size='20'>   Zer0</font>\n"
    "<font color='#33fefe'>  Fearless</font> increases shield recharge delay\n"
    "\t  Kunai don't inflict self damage\n\n"
    "\t\t\t<font size='20'>   Krieg</font>\n"
    "<font color='#33fefe'>  Silence the Voices</font> scales self-hit chance\n"
    "<font color='#33fefe'>  Buzz Axe Bombadier</font> has slag explosions"
)
