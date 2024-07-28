import webbrowser

from unrealsdk import (ConstructObject, FindObject, FStruct,  # type: ignore
                       KeepAlive, LoadPackage, Log, UFunction, UObject)

from ..ModMenu import (EnabledSaveType, Game, Hook, Mods, ModTypes,
                       RegisterMod, SDKMod)

try:
    from ..Structs import AttributeInitializationData, SkillEffectData  # type: ignore
except ImportError:
    webbrowser.open("https://bl-sdk.github.io/requirements/?mod=Melee%20Enhancement&Structs")
    raise


def SetSkillDescription(PC, Skill: str, Desc: str) -> None:
    # Skill descriptions are set in this roundabout way as setting them directly causes a crash
    PC.ConsoleCommand(f"set {Skill} SkillDescription {Desc}")


class MeleeEnhancement(SDKMod):
    Name: str = "Melee Enhancement"
    Author: str = "LaryIsland"
    Description: str = (
        "<font size='26' color='#de5b00'>       Melee Enhancement</font>\n\n"
        "\t\t\t<font size='20'>   Zer0</font>\n"
        "<font color='#33fefe'>  Fearless</font> increases shield recharge delay\n"
        "\t  Kunai don't inflict self damage\n\n"
        "\t\t\t<font size='20'>   Kreig</font>\n"
        "<font color='#33fefe'>  Silence the Voices</font> scales self-hit chance\n"
        "<font color='#33fefe'>  Buzz Axe Bombadier</font> has slag explosions"
    )
    Version: str = "1.0"

    SupportedGames: Game = Game.BL2
    Types: ModTypes = ModTypes.Gameplay
    SaveEnabledState: EnabledSaveType = EnabledSaveType.LoadOnMainMenu

    SettingsInputs = SDKMod.SettingsInputs.copy()
    SettingsInputs["G"] = "GitHub"

    def SettingsInputPressed(self, action: str) -> None:
        if action == "GitHub":
            webbrowser.open("https://github.com/LaryIsland/bl-sdk-mods/tree/main/MeleeEnhancement")
        else:
            super().SettingsInputPressed(action)

    @Hook("WillowGame.PlayerSkillTree.Initialize")
    def InjectSkillChanges(self, caller: UObject, function: UFunction, params: FStruct) -> bool:
        className = caller.Outer.PlayerClass.CharacterNameId.CharacterClassId.ClassName
        if className == "Assassin":
            LoadPackage("GD_Lilac_Psycho_Streaming_SF")
            Fearless_SkillDefinition = FindObject("SkillDefinition", "GD_Assassin_Skills.Cunning.Fearless")

            Fearless_SkillDefinition.SkillEffectDefinitions = [
                SkillEffectData(SkillEffectDefinition) for SkillEffectDefinition
                in Fearless_SkillDefinition.SkillEffectDefinitions] + \
                [SkillEffectData(
                    AttributeToModify=FindObject(
                        "ResourcePoolAttributeDefinition",
                        "D_Attributes.ShieldResourcePool.ShieldOnIdleRegenerationDelay"
                    ),
                    EffectTarget=1,
                    ModifierType=2,
                    BaseModifierValue=AttributeInitializationData(
                        BaseValueConstant=1.0,
                        BaseValueAttribute=None,
                        InitializationDefinition=None,
                        BaseValueScaleConstant=1.0
                    ),
                    GradeToStartApplyingEffect=1,
                    PerGradeUpgradeInterval=1,
                    PerGradeUpgrade=AttributeInitializationData(
                        BaseValueConstant=1.0,
                        BaseValueAttribute=None,
                        InitializationDefinition=None,
                        BaseValueScaleConstant=1.0
                    ),
                )]

            SetSkillDescription(caller.Outer,
                                "GD_Assassin_Skills.Cunning.Fearless", Fearless_SkillDefinition.SkillDescription
                                + " Additionally, increases the delay before your shields "
                                + "[skill]start to recharge[-skill] after being depleted.")

            Fearless_SkillDefinition.SkillEffectPresentations = [
                SkillEffectPresentation for SkillEffectPresentation
                in Fearless_SkillDefinition.SkillEffectPresentations] \
                + [FindObject(
                    "SkillDefinition",
                    "GD_Lilac_Skills_Mania.Skills.EmbraceThePain"
                ).SkillEffectPresentations[1]
            ]

            FindObject(
                "Behavior_SpawnProjectile",
                "GD_Assassin_Skills.ActionSkill.Skill_Stealth:BehaviorProviderDefinition_0.Behavior_SpawnProjectile_0"
            ).bInflictRadiusDamageOnOwner = False

        elif className == "Psycho":
            SilenceTheVoices_SkillDefinition = FindObject(
                "SkillDefinition",
                "GD_Lilac_Skills_Mania.Skills.SilenceTheVoices"
            )

            SelfHitPresentation = ConstructObject(Class="AttributePresentationDefinition",
                                                  Outer=SilenceTheVoices_SkillDefinition,
                                                  Name="AttributePresentationDefinition_2",
                                                  Template=SilenceTheVoices_SkillDefinition.SkillEffectPresentations[1]
                                                  )
            KeepAlive(SelfHitPresentation)
            SelfHitPresentation.ObjectFlags.B |= 4
            SelfHitPresentation.bDisplayPercentAsFloat = True
            SelfHitPresentation.RoundingMode = 0

            SilenceTheVoices_SkillDefinition.SkillEffectPresentations[1] = SelfHitPresentation

            SilenceTheVoices_SkillDefinition.SkillEffectDefinitions[0].PerGradeUpgrade.BaseValueConstant = -0.013333333
            SilenceTheVoices_SkillDefinition.SkillEffectDefinitions[0].PerGradeUpgradeInterval = 1

            BuzzaxeExplosion = FindObject(
                "Behavior_Explode",
                "GD_Lilac_SkillsBase.Buzzaxe.Projectile_Buzzaxe:BehaviorProviderDefinition_0.Behavior_Explode_6"
            )

            BuzzaxeExplosion.InstigatorSelfDamageScale /= 3
            BuzzaxeExplosion.Definition = FindObject("ExplosionDefinition", "GD_Explosions.Slag.Explosion_SlagMaster")

            SetSkillDescription(caller.Outer,
                                "GD_Lilac_Skills_Bloodlust.Skills.BuzzAxeBombadier",
                                FindObject(
                                    "SkillDefinition",
                                    "GD_Lilac_Skills_Bloodlust.Skills.BuzzAxeBombadier"
                                ).SkillDescription[:-1] + " and [skill]slags[-skill] nearby enemies."
                                )

        return True


instance = MeleeEnhancement()

if __name__ == "__main__":
    Log(f"[{instance.Name}] Manually loaded")
    for mod in Mods:
        if mod.Name == instance.Name:
            if mod.IsEnabled:
                mod.Disable()
            Mods.remove(mod)
            Log(f"[{instance.Name}] Removed last instance")

            # Fixes inspect.getfile()
            instance.__class__.__module__ = mod.__class__.__module__
            break

RegisterMod(instance)
