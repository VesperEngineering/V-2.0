from vesper.dashboard.app import DashboardApp
from vesper.dashboard.model_runs import best_oos_so_far, model_run_rows, promotion_oos_ic


def test_model_run_rows_include_baseline_trials_and_pending_candidate():
    state = {
        "baseline": {"out_of_sample_ic": 0.0324, "rank_ic": 0.03, "ranking_spread": 0.0026},
        "accepted": [
            {
                "run": 2,
                "candidate": {"out_of_sample_ic": 0.04, "rank_ic": 0.04, "ranking_spread": 0.003},
            },
        ],
        "rejected": [
            {
                "run": 1,
                "candidate": {"out_of_sample_ic": 0.031, "rank_ic": 0.02, "ranking_spread": 0.001},
            },
        ],
        "pending": {"run": 3, "parameters": {"n_estimators": 40}},
    }

    rows = model_run_rows(state)

    assert [(row["run"], row["status"]) for row in rows] == [
        (0, "BASELINE"),
        (1, "REJECTED"),
        (2, "ACCEPTED"),
        (3, "RUNNING"),
    ]
    assert rows[0]["oos_ic"] == 0.0324
    assert rows[3]["oos_ic"] is None


def test_promotion_oos_ic_uses_the_recorded_acceptance_gate():
    state = {
        "rejected": [{"baseline_comparison": {"minimum_out_of_sample_ic": 0.0354}}],
    }

    assert promotion_oos_ic(state) == 0.0354


def test_best_oos_so_far_keeps_the_research_leader_until_beaten():
    rows = [
        {"run": 0, "oos_ic": 0.0324},
        {"run": 1, "oos_ic": 0.0310},
        {"run": 2, "oos_ic": 0.0332},
        {"run": 3, "oos_ic": 0.0328},
    ]

    assert best_oos_so_far(rows) == [0.0324, 0.0324, 0.0332, 0.0332]


def test_dashboard_model_runs_button_shows_evidence_in_main_window(tk_root):
    app = DashboardApp(tk_root)

    app.model_runs_btn.invoke()
    tk_root.update_idletasks()

    assert app._model_window is app._model_runs_frame
    assert app._model_runs_frame.winfo_manager() == "pack"
    assert app._main.winfo_manager() == ""
    app._close_model_runs()
    assert app._model_window is None
    assert app._main.winfo_manager() == "pack"
