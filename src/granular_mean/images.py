from __future__ import annotations


UNPUBLISHED_DIGEST = "0" * 64

DEFAULT_AGENT_IMAGE = (
    "ghcr.io/cbizon/granular-mean-agent@sha256:"
    "a8266fcda7c16d377a2557ef8221fa080240616498185f13677ec6fc29a34fdd"
)
DEFAULT_CONTROLLER_IMAGE = (
    "ghcr.io/cbizon/granular-mean-controller@sha256:"
    "d77903f27b14f83205ff0a8fb3142c943e1b25ad6c96ea04e365e5ea10b23fe1"
)
DEFAULT_EVALUATOR_IMAGE = DEFAULT_CONTROLLER_IMAGE
DEFAULT_SQUID_IMAGE = (
    "ubuntu/squid@sha256:"
    "6a097f68bae708cedbabd6188d68c7e2e7a38cedd05a176e1cc0ba29e3bbe029"
)

DEFAULT_REFERENCE_UPLOAD_IMAGE = DEFAULT_CONTROLLER_IMAGE

RETIRED_AGENT_IMAGES = (
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "8b785dc13f0c52ad53ddd59088b210c64327dd1dfedd38df4b5d952f76c99868"
    ),
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "487049af74c582eaf3af204af8d86a05fd57918ee6edfdae2409742c9699975d"
    ),
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "b2065cc9f29fea74ee7fb0200192b5e725e54921312be62e39f15e89dc40a6bd"
    ),
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "cf2f1492fe222dfb5e332222d249c4ee68ebeef76e7d4462198f993065f38a61"
    ),
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "3a9a61ea9abf4e3e29bce0a29a1bb98c366d60e6ca311cc70e226987c4a28747"
    ),
    (
        "ghcr.io/cbizon/granular-mean-agent@sha256:"
        "38eeb7872ddc0aac27d77dff1bd127b925340f481ce7c17b631657ab5dd4ccf1"
    ),
)
RETIRED_AGENT_IMAGE = RETIRED_AGENT_IMAGES[0]
RETIRED_CONTROLLER_IMAGES = (
    (
        "ghcr.io/cbizon/granular-mean-controller@sha256:"
        "aa1787e6b82b8eb88df1d211b5b9663a8158f9e7a34681420e3dca5c8b47b30e"
    ),
    (
        "ghcr.io/cbizon/granular-mean-controller@sha256:"
        "ee071a0b3f166157b4f9c920b4a1157a5e08674746c8773d1ff47f3d2fd08be2"
    ),
)
RETIRED_EVALUATOR_IMAGES = (
    (
        "ghcr.io/cbizon/granular-mean-evaluator@sha256:"
        "6a2cdcb2a2e66ccbef8451f29dbdb246f3fa888052d24004f50b034457e19f05"
    ),
    (
        "ghcr.io/cbizon/granular-mean-evaluator@sha256:"
        "77c4742436b703526c779565f8dc749156cc48cf661363241e93d24f8fad1b2d"
    ),
)
RETIRED_EVALUATOR_IMAGE = RETIRED_EVALUATOR_IMAGES[0]


def is_unpublished_image(image: str) -> bool:
    return image.endswith(f"sha256:{UNPUBLISHED_DIGEST}")
