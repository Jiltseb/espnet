# coding: utf-8

import argparse
import pytest
import torch

from espnet.nets.pytorch_backend.e2e_asr_transducer import E2E


def make_train_args(**kwargs):
    train_defaults = dict(
        transformer_init="pytorch",
        etype="transformer",
        transformer_enc_input_layer="conv2d",
        transformer_enc_self_attn_type="selfattn",
        transformer_enc_positional_encoding_type="abs_pos",
        transformer_enc_pw_activation_type="relu",
        transformer_enc_conv_mod_activation_type="relu",
        enc_block_arch=[{"type": "transformer", "d_hidden": 2, "d_ff": 2, "heads": 1}],
        enc_block_repeat=1,
        dtype="transformer",
        transformer_dec_input_layer="embed",
        dec_block_arch=[{"type": "transformer", "d_hidden": 2, "d_ff": 2, "heads": 1}],
        dec_block_repeat=1,
        transformer_dec_pw_activation_type="relu",
        dropout_rate_embed_decoder=0.0,
        joint_dim=2,
        joint_activation_type="tanh",
        mtlalpha=1.0,
        trans_type="warp-transducer",
        rnnt_mode="rnnt_mode",
        char_list=["a", "e", "i", "o", "u"],
        sym_space="<space>",
        sym_blank="<blank>",
        report_cer=False,
        report_wer=False,
        search_type="default",
        score_norm_transducer=False,
        beam_size=1,
        nbest=1,
        verbose=0,
        outdir=None,
        rnnlm=None,
    )
    train_defaults.update(kwargs)

    return argparse.Namespace(**train_defaults)


def make_recog_args(**kwargs):
    recog_defaults = dict(
        batchsize=0,
        beam_size=1,
        nbest=1,
        verbose=0,
        search_type="default",
        nstep=1,
        max_sym_exp=2,
        u_max=5,
        prefix_alpha=2,
        score_norm_transducer=True,
        rnnlm=None,
    )
    recog_defaults.update(kwargs)

    return argparse.Namespace(**recog_defaults)


def get_default_scope_inputs():
    bs = 2
    idim = 12
    odim = 5

    ilens = [12, 4]
    olens = [5, 4]

    return bs, idim, odim, ilens, olens


def prepare(args):
    bs, idim, odim, ilens, olens = get_default_scope_inputs()
    n_token = odim - 1

    model = E2E(idim, odim, args)

    x = torch.randn(bs, max(ilens), idim)
    y = (torch.rand(bs, max(olens)) * n_token % n_token).long()

    for i in range(bs):
        x[i, ilens[i] :] = -1
        y[i, olens[i] :] = model.ignore_id

    data = []
    for i in range(bs):
        data.append(
            (
                "utt%d" % i,
                {
                    "input": [{"shape": [ilens[i], idim]}],
                    "output": [{"shape": [olens[i]]}],
                },
            )
        )

    return model, x, torch.tensor(ilens), y, data


@pytest.mark.parametrize(
    "train_dic, recog_dic",
    [
        ({}, {}),
        ({"enc_block_repeat": 2}, {}),
        ({"dec_block_repeat": 2}, {}),
        (
            {
                "enc_block_arch": [
                    {
                        "type": "conformer",
                        "d_hidden": 2,
                        "d_ff": 2,
                        "heads": 1,
                        "macaron_style": True,
                        "use_conv_mod": True,
                        "conv_mod_kernel": 1,
                    }
                ],
            },
            {},
        ),
        (
            {
                "enc_block_arch": [
                    {
                        "type": "conformer",
                        "d_hidden": 2,
                        "d_ff": 2,
                        "heads": 2,
                        "macaron_style": False,
                        "use_conv_mod": True,
                        "conv_mod_kernel": 1,
                        "transformer_enc_pw_activation_type": "swish",
                        "transformer_enc_conv_mod_activation_type": "relu",
                    }
                ],
            },
            {"transformer_dec_pw_activation_type": "swish"},
        ),
        (
            {
                "enc_block_arch": [
                    {
                        "type": "tdnn",
                        "idim": 2,
                        "odim": 2,
                        "ctx_size": 3,
                        "dilation": 1,
                        "stride": 1,
                        "dropout-rate": 0.3,
                    },
                    {
                        "type": "transformer",
                        "d_hidden": 2,
                        "d_ff": 2,
                        "heads": 1,
                        "dropout-rate": 0.3,
                        "att-dropout-rate": 0.2,
                        "pos-dropout-rate": 0.1,
                    },
                ],
            },
            {},
        ),
        (
            {
                "dec_block_arch": [
                    {"type": "causal-conv1d", "idim": 2, "odim": 2, "kernel_size": 3},
                    {"type": "transformer", "d_hidden": 2, "d_ff": 2, "heads": 1},
                ]
            },
            {},
        ),
        ({"transformer_enc_pw_activation_type": "swish"}, {}),
        ({"transformer_enc_pw_activation_type": "hardtanh"}, {}),
        ({"transformer_dec_pw_activation_type": "swish"}, {}),
        ({"transformer_dec_pw_activation_type": "hardtanh"}, {}),
        ({"joint_activation_type": "relu"}, {}),
        ({"joint_activation_type": "swish"}, {}),
        ({"transformer_enc_input_layer": "vgg2l"}, {}),
        ({"transformer_enc_input_layer": "linear"}, {}),
        ({"report_cer": True, "report_wer": True}, {}),
        ({"report_cer": True, "beam_size": 2}, {}),
        ({}, {"beam_size": 2}),
        ({}, {"beam_size": 2, "nbest": 2, "score_norm_transducer": False}),
        ({}, {"beam_size": 2, "search_type": "nsc", "nstep": 3, "prefix_alpha": 1}),
        ({}, {"beam_size": 2, "search_type": "tsd", "max_sym_exp": 3}),
        ({}, {"beam_size": 2, "search_type": "alsd"}),
        ({}, {"beam_size": 2, "search_type": "alsd", "u_max": 10}),
    ],
)
def test_sa_transducer_trainable_and_decodable(train_dic, recog_dic):
    train_args = make_train_args(**train_dic)
    recog_args = make_recog_args(**recog_dic)

    model, x, ilens, y, data = prepare(train_args)

    optim = torch.optim.Adam(model.parameters(), 0.01)
    loss = model(x, ilens, y)

    optim.zero_grad()
    loss.backward()
    optim.step()

    with torch.no_grad():
        nbest = model.recognize(x[0, : ilens[0]].numpy(), recog_args)

        print(y[0])
        print(nbest[0]["yseq"][1:-1])


def test_calculate_plot_attention():
    from espnet.nets.pytorch_backend.transformer import plot

    train_args = make_train_args(report_cer=True)

    model, x, ilens, y, data = prepare(train_args)

    attn_dict = model.calculate_all_attentions(x[0:1], ilens[0:1], y[0:1])
    plot.plot_multi_head_attention(data, attn_dict, "/tmp/espnet-test")
