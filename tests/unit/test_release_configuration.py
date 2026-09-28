"""Release-safety checks for deployment and automation configuration."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_render_blueprint_disables_moving_branch_deploys() -> None:
    path = REPO_ROOT / "render.yaml"
    config = _load_yaml(path)
    service = config["services"][0]
    environment = {item["key"]: item for item in service["envVars"]}

    assert service["plan"] == "free"
    assert service["autoDeploy"] == "false"
    assert environment["PLAID_ENV"]["value"] == "sandbox"
    assert "Hobby/Sandbox only" in path.read_text(encoding="utf-8")


def test_database_write_workflow_checks_out_exact_reviewed_sha() -> None:
    workflow = _load_yaml(REPO_ROOT / ".github/workflows/nightly-sync.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    steps = workflow["jobs"]["sync"]["steps"]
    by_name = {step["name"]: step for step in steps}
    names = list(by_name)

    reviewed_input = inputs["reviewed_commit_sha"]
    assert reviewed_input["type"] == "string"
    assert reviewed_input["required"] == "false"
    assert "40-character" in reviewed_input["description"]

    validate = by_name["Validate reviewed commit input"]
    checkout = by_name["Check out source"]
    verify = by_name["Verify checked-out commit"]
    migrations = by_name["Run database migrations"]

    assert "^[0-9a-f]{40}$" in validate["run"]
    assert checkout["with"]["ref"] == "${{ inputs.reviewed_commit_sha }}"
    assert "git rev-parse HEAD" in verify["run"]
    assert names.index(validate["name"]) < names.index(checkout["name"])
    assert names.index(verify["name"]) < names.index(migrations["name"])


def test_telegram_dispatch_discloses_possible_transaction_detail() -> None:
    workflow = _load_yaml(REPO_ROOT / ".github/workflows/nightly-sync.yml")
    description = workflow["on"]["workflow_dispatch"]["inputs"][
        "send_telegram_summary"
    ]["description"]

    for field in ("institution", "merchant", "date", "amount"):
        assert field in description


def test_database_integration_target_uses_synthetic_configuration() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("test-database-integration:", 1)[1].split(
        "test-plaid-integration:", 1
    )[0]

    assert "BUDGET_ME_ALLOW_DATABASE_TESTS" in target
    assert "BUDGET_ME_TEST_DATABASE_URL" in target
    assert "test_database_target_is_disposable" in target
    assert "APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=" in target
    assert "BUDGET_ME_DISABLE_DOTENV=1" in target
