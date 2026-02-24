"""Demo UI specifications for testing without API calls."""

DEMO_SPEC = {
    "contract_id": "demo-contract",
    "title": "Financial Contract - Fee Structure",
    "description": "Payment management services agreement with fee schedules",
    "components": [
        {
            "type": "Section",
            "props": {"title": "Document Information"},
            "children": [
                {
                    "type": "Card",
                    "props": {"variant": "outlined"},
                    "children": [
                        {
                            "type": "KeyValueList",
                            "data_bindings": {
                                "items": {"path": "document_info"}
                            }
                        }
                    ]
                }
            ]
        },
        {
            "type": "Section",
            "props": {"title": "Fee Structure"},
            "children": [
                {
                    "type": "Grid",
                    "props": {"columns": 2, "gap": "md"},
                    "children": [
                        {
                            "type": "FeeCard",
                            "data_bindings": {
                                "fee_name": {"path": "fees_and_rates[0].fee_name"},
                                "amount": {"path": "fees_and_rates[0].amount", "transform": "formatPercentage"},
                                "currency": {"path": "fees_and_rates[0].currency"},
                                "calculation_method": {"path": "fees_and_rates[0].calculation_method"},
                                "conditions": {"path": "fees_and_rates[0].conditions"}
                            },
                            "style": {"color": "warning"}
                        },
                        {
                            "type": "FeeCard",
                            "data_bindings": {
                                "fee_name": {"path": "fees_and_rates[1].fee_name"},
                                "amount": {"path": "fees_and_rates[1].amount", "transform": "formatPercentage"},
                                "currency": {"path": "fees_and_rates[1].currency"},
                                "calculation_method": {"path": "fees_and_rates[1].calculation_method"},
                                "conditions": {"path": "fees_and_rates[1].conditions"}
                            },
                            "style": {"color": "warning"}
                        }
                    ]
                }
            ]
        },
        {
            "type": "Section",
            "props": {"title": "Additional Information"},
            "children": [
                {
                    "type": "Grid",
                    "props": {"columns": 3, "gap": "md"},
                    "children": [
                        {
                            "type": "Card",
                            "props": {"title": "Supported Currencies"},
                            "children": [
                                {
                                    "type": "BadgeList",
                                    "data_bindings": {
                                        "items": {"path": "supported_currencies"}
                                    },
                                    "style": {"color": "primary"}
                                }
                            ]
                        },
                        {
                            "type": "Card",
                            "props": {"title": "Supported Regions"},
                            "children": [
                                {
                                    "type": "BadgeList",
                                    "data_bindings": {
                                        "items": {"path": "supported_regions"}
                                    },
                                    "style": {"color": "success"}
                                }
                            ]
                        },
                        {
                            "type": "Card",
                            "props": {"title": "Payment Terms"},
                            "children": [
                                {
                                    "type": "KeyValueList",
                                    "data_bindings": {
                                        "items": {"path": "payment_terms"}
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "type": "Section",
            "props": {"title": "All Fees"},
            "children": [
                {
                    "type": "Table",
                    "data_bindings": {
                        "data": {"path": "fees_and_rates"}
                    },
                    "props": {"showHeader": True}
                }
            ]
        }
    ],
    "metadata": {
        "generated_by": "demo_mode",
        "note": "This is a demo UI specification for testing"
    }
}
