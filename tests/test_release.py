"""Vérifie .github/scripts/check_release.py : tag, manifest et liens du changelog."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "check_release.py"
TAGS = {"1.4.1", "1.5.0", "1.5.1", "1.6.0"}
BODY = "**Full changelog:** https://github.com/o/r/compare/1.5.1...1.6.0"


def _load():
    spec = importlib.util.spec_from_file_location("check_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release(check):
    run = _load().check

    print("== une release conforme ==")
    check("1.6.0", run("1.6.0", "v1.6.0", BODY, "1.6.0", TAGS), ([], []))
    check("lien entre crochets markdown",
          run("1.6.0", "v1.6.0", "[diff](https://github.com/o/r/compare/1.5.1...1.6.0)",
              "1.6.0", TAGS), ([], []))

    print("== erreurs : ce qui trompe HACS ou le lecteur ==")
    errors, _ = run("1.5.1", "v1.5.1",
                    "https://github.com/o/r/compare/v1.5.0...v1.5.1", "1.5.1", TAGS)
    check("le lien de la 1.5.1 d'origine est refusé",
          [e for e in errors if "not a tag" in e],
          ["changelog link compare/v1.5.0...v1.5.1 names 'v1.5.0', which is not a tag",
           "changelog link compare/v1.5.0...v1.5.1 names 'v1.5.1', which is not a tag"])
    errors, _ = run("v1.6.0", "v1.6.0", BODY, "1.6.0", TAGS | {"v1.6.0"})
    check("tag avec un v", any("not X.Y.Z" in e for e in errors), True)
    errors, _ = run("1.6.0", "v1.6.0", BODY, "1.5.1", TAGS)
    check("manifest pas à jour", errors,
          ["manifest.json says version '1.5.1', the tag is '1.6.0'"])
    errors, _ = run("1.6.0", "v1.6.0",
                    "https://github.com/o/r/compare/1.5.0...1.5.1", "1.6.0", TAGS)
    check("lien qui ne finit pas sur la release",
          any("does not end at this release" in e for e in errors), True)

    print("== avertissements : des conventions ==")
    errors, warnings = run("1.6.0", "1.6.0", BODY, "1.6.0", TAGS)
    check("titre sans v : pas une erreur", errors, [])
    check("titre sans v : signalé", warnings, ["title '1.6.0', expected 'v1.6.0'"])
    errors, warnings = run("1.6.0", "v1.6.0",
                           "https://github.com/o/r/compare/1.5.0...1.6.0", "1.6.0", TAGS)
    check("lien depuis une release plus ancienne", (errors, warnings),
          ([], ["changelog link starts at '1.5.0', the previous release is '1.5.1'"]))
    errors, warnings = run("1.6.0", "v1.6.0", "Pas de lien.", "1.6.0", TAGS)
    check("pas de lien", (errors, len(warnings)), ([], 1))
    check.assert_ok()
