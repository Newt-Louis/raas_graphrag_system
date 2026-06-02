import{E as e,G as t,H as n,O as r,S as i,_ as a,c as o,d as s,ft as c,g as l,gt as u,i as d,s as f,t as p,u as m,w as h,x as g}from"./_plugin-vue_export-helper-OXDhrhLV.js";import{n as _,xt as v}from"./service-CFUZAYLU.js";import{r as y,t as b,u as x}from"./baseinput-FqvKYQ3_.js";import{n as S}from"./index-DiJONGrn.js";var C=_.extend({name:`textarea`,style:`
    .p-textarea {
        font-family: inherit;
        font-feature-settings: inherit;
        font-size: 1rem;
        color: dt('textarea.color');
        background: dt('textarea.background');
        padding-block: dt('textarea.padding.y');
        padding-inline: dt('textarea.padding.x');
        border: 1px solid dt('textarea.border.color');
        transition:
            background dt('textarea.transition.duration'),
            color dt('textarea.transition.duration'),
            border-color dt('textarea.transition.duration'),
            outline-color dt('textarea.transition.duration'),
            box-shadow dt('textarea.transition.duration');
        appearance: none;
        border-radius: dt('textarea.border.radius');
        outline-color: transparent;
        box-shadow: dt('textarea.shadow');
    }

    .p-textarea:enabled:hover {
        border-color: dt('textarea.hover.border.color');
    }

    .p-textarea:enabled:focus {
        border-color: dt('textarea.focus.border.color');
        box-shadow: dt('textarea.focus.ring.shadow');
        outline: dt('textarea.focus.ring.width') dt('textarea.focus.ring.style') dt('textarea.focus.ring.color');
        outline-offset: dt('textarea.focus.ring.offset');
    }

    .p-textarea.p-invalid {
        border-color: dt('textarea.invalid.border.color');
    }

    .p-textarea.p-variant-filled {
        background: dt('textarea.filled.background');
    }

    .p-textarea.p-variant-filled:enabled:hover {
        background: dt('textarea.filled.hover.background');
    }

    .p-textarea.p-variant-filled:enabled:focus {
        background: dt('textarea.filled.focus.background');
    }

    .p-textarea:disabled {
        opacity: 1;
        background: dt('textarea.disabled.background');
        color: dt('textarea.disabled.color');
    }

    .p-textarea::placeholder {
        color: dt('textarea.placeholder.color');
    }

    .p-textarea.p-invalid::placeholder {
        color: dt('textarea.invalid.placeholder.color');
    }

    .p-textarea-fluid {
        width: 100%;
    }

    .p-textarea-resizable {
        overflow: hidden;
        resize: none;
    }

    .p-textarea-sm {
        font-size: dt('textarea.sm.font.size');
        padding-block: dt('textarea.sm.padding.y');
        padding-inline: dt('textarea.sm.padding.x');
    }

    .p-textarea-lg {
        font-size: dt('textarea.lg.font.size');
        padding-block: dt('textarea.lg.padding.y');
        padding-inline: dt('textarea.lg.padding.x');
    }
`,classes:{root:function(e){var t=e.instance,n=e.props;return[`p-textarea p-component`,{"p-filled":t.$filled,"p-textarea-resizable ":n.autoResize,"p-textarea-sm p-inputfield-sm":n.size===`small`,"p-textarea-lg p-inputfield-lg":n.size===`large`,"p-invalid":t.$invalid,"p-variant-filled":t.$variant===`filled`,"p-textarea-fluid":t.$fluid}]}}}),w={name:`BaseTextarea`,extends:b,props:{autoResize:Boolean},style:C,provide:function(){return{$pcTextarea:this,$parentInstance:this}}};function T(e){"@babel/helpers - typeof";return T=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},T(e)}function E(e,t,n){return(t=D(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function D(e){var t=O(e,`string`);return T(t)==`symbol`?t:t+``}function O(e,t){if(T(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(T(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var k={name:`Textarea`,extends:w,inheritAttrs:!1,observer:null,mounted:function(){var e=this;this.autoResize&&(this.observer=new ResizeObserver(function(){requestAnimationFrame(function(){e.resize()})}),this.observer.observe(this.$el))},updated:function(){this.autoResize&&this.resize()},beforeUnmount:function(){this.observer&&this.observer.disconnect()},methods:{resize:function(){if(this.$el.offsetParent){var e=this.$el.style.height,t=parseInt(e)||0,n=this.$el.scrollHeight;t&&n<t?(this.$el.style.height=`auto`,this.$el.style.height=`${this.$el.scrollHeight}px`):(!t||n>t)&&(this.$el.style.height=`${n}px`)}},onInput:function(e){this.autoResize&&this.resize(),this.writeValue(e.target.value,e)}},computed:{attrs:function(){return g(this.ptmi(`root`,{context:{filled:this.$filled,disabled:this.disabled}}),this.formField)},dataP:function(){return x(E({invalid:this.$invalid,fluid:this.$fluid,filled:this.$variant===`filled`},this.size,this.size))}}},A=[`value`,`name`,`disabled`,`aria-invalid`,`data-p`];function j(t,n,r,i,a,o){return e(),s(`textarea`,g({class:t.cx(`root`),value:t.d_value,name:t.name,disabled:t.disabled,"aria-invalid":t.invalid||void 0,"data-p":o.dataP,onInput:n[0]||=function(){return o.onInput&&o.onInput.apply(o,arguments)}},o.attrs),null,16,A)}k.render=j;function M(){let e=S(),t=n({primaryColor:`#3b82f6`,theme:`light`,apiKey:``});return h(()=>{let n=e.query;n.primary_color&&(t.value.primaryColor=decodeURIComponent(n.primary_color),document.documentElement.style.setProperty(`--primary-color`,t.value.primaryColor)),n.theme&&(t.value.theme=n.theme,document.documentElement.setAttribute(`data-theme`,t.value.theme)),window.addEventListener(`message`,e=>{e.data.type===`UPDATE_THEME`&&document.documentElement.style.setProperty(`--primary-color`,e.data.primaryColor)})}),{config:t}}var N={class:`chat-page`},P={class:`sidebar-head`},F={class:`conversation-list`,"aria-label":`Conversations`},I={class:`conversation-item active`,type:`button`},L={class:`sidebar-footer`},R={class:`chat-workspace`},z={class:`chat-topbar`},B={class:`scope-label`},V={key:0,class:`empty-conversation`},H={key:0,class:`message-avatar`},U=[`title`],W={key:1,class:`citations`},G={key:0},K={key:1,class:`message-row assistant`},q={class:`composer-area`},J={key:0,class:`error-text`},Y=p(a({__name:`EmbedChatView`,setup(a){let p=S();M();let h=n([]),g=n(``),_=n(!1),b=n(``),x=n(!0),C=n(null),w=n($()),T=f(()=>({tenant_id:String(p.query.tenant_id||`tenant-a`),app_id:String(p.query.app_id||`app-a`),collection_id:p.query.collection_id?String(p.query.collection_id):null})),E=f(()=>h.value.find(e=>e.role===`user`)?.content||`New conversation`);async function D(){let e=g.value.trim();if(!e||_.value)return;let t=h.value.filter(e=>!e.failed).slice(-12).map(({role:e,content:t})=>({role:e,content:t}));h.value.push({id:$(),role:`user`,content:e}),g.value=``,_.value=!0,b.value=``,await Z();let n=null;try{let r=await fetch(`/api/v1/chat/completions/stream`,{method:`POST`,headers:{Accept:`text/event-stream`,"Content-Type":`application/json`},body:JSON.stringify({...T.value,session_id:w.value,message:e,history:t})});if(!r.ok){let e=await r.json().catch(()=>({}));throw Error(Q(e,r.statusText))}n={id:$(),role:`assistant`,content:``},h.value.push(n),await O(r,n)}catch(e){let t=e instanceof Error?e.message:`Chat request failed.`;b.value=t,n&&!n.content?(n.content=t,n.failed=!0):h.value.push({id:$(),role:`assistant`,content:t,failed:!0})}finally{_.value=!1,await Z()}}async function O(e,t){if(!e.body)throw Error(`Streaming response body is unavailable.`);let n=e.body.getReader(),r=new TextDecoder,i=``,a=!1;for(;;){let{done:e,value:o}=await n.read();i+=r.decode(o,{stream:!e});let s=i.split(/\r?\n\r?\n/);i=s.pop()||``;for(let e of s)a=j(A(e),t)||a;if(await Z(),e)break}if(i.trim()&&(a=j(A(i),t)||a),!a)throw Error(`Chat stream ended before the completion event.`)}function A(e){let t=`message`,n=[];for(let r of e.split(/\r?\n/))r.startsWith(`event:`)?t=r.slice(6).trim():r.startsWith(`data:`)&&n.push(r.slice(5).trimStart());let r=n.join(`
`);return{event:t,data:r?JSON.parse(r):{}}}function j(e,t){if(e.event===`metadata`){let n=e.data;t.citations=n.citations,t.responseType=n.response_type,t.strategy=n.strategy}else if(e.event===`delta`){let n=e.data;typeof n.text==`string`&&(t.content+=n.text)}else if(e.event===`error`)throw Error(Q(e.data,`Chat stream failed.`));return e.event===`done`}function Y(e){e.key===`Enter`&&!e.shiftKey&&(e.preventDefault(),D())}function X(){h.value=[],g.value=``,b.value=``,w.value=$()}async function Z(){await i(),C.value&&(C.value.scrollTop=C.value.scrollHeight)}function Q(e,t){if(e&&typeof e==`object`&&`detail`in e){let t=e.detail;if(typeof t==`string`)return t}return t}function ee(e){return e===`grounded_answer`?`Document grounded`:e===`refusal`?`Outside document scope`:`Conversation`}function $(){return typeof crypto<`u`&&`randomUUID`in crypto?crypto.randomUUID():`${Date.now()}-${Math.random()}`}return(n,i)=>(e(),s(`main`,N,[o(`aside`,{class:c([`conversation-sidebar`,{hidden:!x.value}])},[o(`div`,P,[l(t(y),{type:`button`,icon:`pi pi-plus`,label:`New chat`,severity:`secondary`,outlined:``,class:`new-chat-button`,onClick:X}),l(t(y),{type:`button`,icon:`pi pi-times`,text:``,rounded:``,severity:`secondary`,"aria-label":`Close sidebar`,class:`mobile-close`,onClick:i[0]||=e=>x.value=!1})]),o(`nav`,F,[o(`button`,I,[i[3]||=o(`i`,{class:`pi pi-comment`,"aria-hidden":`true`},null,-1),o(`span`,null,u(E.value),1)])]),o(`footer`,L,[o(`span`,null,u(T.value.tenant_id),1),o(`strong`,null,u(T.value.app_id),1)])],2),o(`section`,R,[o(`header`,z,[l(t(y),{type:`button`,icon:`pi pi-bars`,text:``,rounded:``,severity:`secondary`,"aria-label":`Open sidebar`,onClick:i[1]||=e=>x.value=!x.value}),i[4]||=o(`strong`,null,`GraphRAG Assistant`,-1),o(`span`,B,u(T.value.collection_id||`All documents`),1)]),o(`div`,{ref_key:`conversationRef`,ref:C,class:`conversation-stream`,"aria-live":`polite`},[h.value.length?m(``,!0):(e(),s(`section`,V,[...i[5]||=[o(`span`,{class:`assistant-mark`},`R`,-1),o(`h1`,null,`How can I help?`,-1)]])),(e(!0),s(d,null,r(h.value,t=>(e(),s(`article`,{key:t.id,class:c([`message-row`,t.role])},[t.role===`assistant`?(e(),s(`div`,H,`R`)):m(``,!0),o(`div`,{class:c([`message-content`,{failed:t.failed}])},[t.role===`assistant`&&t.responseType?(e(),s(`span`,{key:0,class:c([`response-type`,t.responseType]),title:t.strategy},u(ee(t.responseType)),11,U)):m(``,!0),o(`p`,null,u(t.content),1),t.citations?.length?(e(),s(`details`,W,[o(`summary`,null,u(t.citations.length)+` sources`,1),o(`ol`,null,[(e(!0),s(d,null,r(t.citations,n=>(e(),s(`li`,{key:`${t.id}-${n.reference}`},[o(`strong`,null,`[`+u(n.reference)+`] `+u(n.filename||n.document_id),1),n.similarity===null?m(``,!0):(e(),s(`span`,G,` similarity `+u(n.similarity.toFixed(3)),1)),o(`p`,null,u(n.excerpt),1)]))),128))])])):m(``,!0)],2)],2))),128)),_.value?(e(),s(`article`,K,[...i[6]||=[o(`div`,{class:`message-avatar`},`R`,-1),o(`div`,{class:`loading-dots`,"aria-label":`Loading`},[o(`span`),o(`span`),o(`span`)],-1)]])):m(``,!0)],512),o(`footer`,q,[o(`form`,{class:`composer`,onSubmit:v(D,[`prevent`])},[l(t(k),{modelValue:g.value,"onUpdate:modelValue":i[2]||=e=>g.value=e,"auto-resize":``,rows:`1`,placeholder:`Message GraphRAG Assistant`,"aria-label":`Message`,onKeydown:Y},null,8,[`modelValue`]),l(t(y),{type:`submit`,icon:`pi pi-arrow-up`,rounded:``,"aria-label":`Send message`,disabled:!g.value.trim()||_.value,loading:_.value},null,8,[`disabled`,`loading`])],32),b.value?(e(),s(`p`,J,u(b.value),1)):m(``,!0)])])]))}}),[[`__scopeId`,`data-v-3de9ce06`]]);export{Y as default};