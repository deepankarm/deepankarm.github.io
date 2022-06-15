---
title: "Jina ❤️ Serverless"
date: 2022-06-15T17:49:55+05:30
description: Serverless experimentation with Jina
tags:
  - jina
  - serverless
  - kubernetes
---

---

## What is Jina?

From the [Docs](https://docs.jina.ai/)

> Jina is a framework that empowers anyone to build cross-modal and multi-modal applications on the cloud.

---

## What is serverless?

From [Wikipedia](https://en.wikipedia.org/wiki/Serverless_computing)

> Serverless computing is a cloud computing execution model in which the cloud provider allocates machine resources on demand, taking care of the servers on behalf of their customers.

Also,

> "Serverless" is a misnomer in the sense that servers are still used by cloud service providers to execute code for developers. However, developers of serverless applications are not concerned with capacity planning, configuration, management, maintenance, fault tolerance, or scaling of containers, VMs, or physical servers.

---

## Why do the Jina users care?

- No headache of setting the [right number of replicas](https://docs.jina.ai/how-to/scale-out/#scale-out-your-executor).
- Scale-to-0 saves a lot of cost, especially when you're starting to host your app.
- Many use cases in Jina doesn't need [Executors](https://docs.jina.ai/fundamentals/executor/) or [Gateway](https://docs.jina.ai/fundamentals/gateway/) to be always alive.
- Serverless allows invocations to be "event-driven".

---

## What is this demo about?

We'll use [Knative serving](https://knative.dev/docs/) along with [Linkerd service mesh](https://linkerd.io/2.11/overview/) & show

- How does serverless work in a K8S world?
- How simple it is to enable autoscaling (from 0 to N) in jina?

---

## Why Knative?

Knative allows us to scale from 0 to N, based on

- [concurrency](https://knative.dev/docs/serving/autoscaling/concurrency/) or [rps](https://knative.dev/docs/serving/autoscaling/rps-target/).
- Set min / max number of replicas per deployment.
- Supports [HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) (Resource metric based 1-to-N scaling provided by K8S) as well.
- Easily integrate with many Ingress controllers.

---

## Demo

As a first step, please clone [jina-serverless-demo](https://github.com/deepankarm/jina-serverless-demo.git), which has the necessary scripts for the demo.

### Set-up

> You can skip this step if you already have a k8s cluster & setup knative / linkerd components.

Let's start by setting up a local environment where serverless machinery can be demonstrated. Following script installs

- `kubectl`, `kind` & `linkerd` CLI, if not already installed.
- A local `kind` cluster named `jina-serverless`.
- `Knative` components
- `Kourier` Ingress for Knative
- `Linkerd` components
- Patch `Knative` & `Kourier` deployments with `Linkerd` service-mesh. [Read this awesome doc!](https://linkerd.io/2020/03/23/serverless-service-mesh-with-knative-and-linkerd/)

```bash
bash setup.sh
```

---

### Define an Executor & a Flow

Let's write a dummy `HeavyExecutor` which sleeps for 3 seconds every time it receives a new request. This can be replaced with any Executor from [Jina Hub](https://hub.jina.ai/).

```python
# HeavyExecutor/executor.py
from jina import DocumentArray, Executor, requests

class HeavyExecutor(Executor):
    @requests
    def foo(self, docs: DocumentArray, **kwargs):
        time.sleep(3)
```

```yaml
# flow.yml
jtype: Flow
executors:
  - name: heavy_executor
    uses: jinahub+docker://HeavyExecutor
```

---

### Convert Flow to K8S yaml

Now that we have the setup done, let's use the jina CLI to export a dummy Flow yaml into K8S specific yamls.

```bash
$ jina export kubernetes flow.yml jina-sls --k8s-namespace jina-sls
# K8s yaml files have been created under jina-sls. You can use it by running kubectl apply -R -f jina-sls

$ tree jina-sls
jina-sls
├── gateway
│   └── gateway.yml
└── heavy_executor
    └── heavy-executor.yml

```

---

### Convert to Knative yaml

> This step is temporary and will be implemented as a [feature](https://github.com/jina-ai/jina/issues/4924) in Jina.

Knative doesn't understand K8S `Deployment` & `Service` resources and implements a `Service` resource under `serving.knative.dev/v1` CRD. Let's convert the K8S yamls to Knative yamls using a helper script.

```bash
kubectl create namespace jina-sls
kubectl apply -R -f $(python kn/change_to_kn.py jina-sls)
```

We might need to wait a bit until all knative objects are setup in addition to the deployments in `jina-sls` namespace. Before any Client sends requests to the Gateway, let's check & wait until each deployment has 0 replicas.

<p align="center">
<a href="#"><img src="/images/wait-until-0.png" alt="0 replicas" width="60%"></a>
</p>

---

### Gateway URL

To check the URL of the Gateway, you can use the following command.

```bash
$ kubectl get ksvc -n jina-sls gateway --no-headers -o custom-columns="URL:.status.url"
http://gateway.jina-sls.127.0.0.1.sslip.io
```

Note that, the URL here is provided by Knative & hence starts with `http`. But it is a polyglot Gateway & accepts all 3 protocols of requests supported by jina (gRPC, WebSockets & HTTP), just by passing the right [URL scheme](https://docs.jina.ai/fundamentals/flow/client/#connect:~:text=You%20can%20define%20these%20parameters%20by%20passing%20a%20valid%20URI%20scheme%20as%20part%20of%20the%20host%20argument%3A).

---

### Let's send requests to the Flow that doesn't exist!

Alright. It took a lot of setup, but now we are ready to see what the fuss is about serverless.

Let's send just 1 request using `jina.Client` & keep an eye on the number of replicas per deployment.

```python
from jina import Client, DocumentArray

Client(host='grpc://gateway.jina-sls.127.0.0.1.sslip.io').post(
    on='/',
    inputs=DocumentArray.empty(2)
)
```

We can observe new replicas popping up for both `gateway` & `heavy-executor` after request is sent via the Client.

<p align="center">
<a href="#"><img src="/images/1-request.gif" alt="Scale from 0" width="90%"></a>
</p>

Now, let's start 10 concurrent Clients that will send requests to the Gateway.

```bash
python load.py 10
```

Note the following.

- As soon as we run the `load.py` script with 10 concurrent clients, new replicas of the `gateway` & `heavy-executor` start spawning.
- After a cool down period, all deployments reach the original state of 0 replicas each.

<p align="center">
<a href="#"><img src="/images/scale-to-10.gif" alt="Scale to 10" width="90%"></a>
</p>

---

## So what?

Whew! Unfortunately, that was a lot of text. I'll try to pull up a few dashboards for the next blog.

- Worry only about the code, and let Knative handle the scaling.
- Best of both worlds - containers + serverless, with 0 headache for the developer.
- Pipeline of invocations with gRPC, REST or Websocket Gateways.
- Does your indexing workload get triggered by Events? Think serverless.

Go, scale your multimodal application using Jina!
